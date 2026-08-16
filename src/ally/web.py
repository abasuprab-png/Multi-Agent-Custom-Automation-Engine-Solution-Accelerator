"""Outside-in discovery. Search and fetch are ports; hits are never ground truth."""

from __future__ import annotations

import json
import os
from typing import Protocol
from urllib.parse import urlparse

import httpx

from ally.contracts import HumanInput, InboundEnvelope
from ally.enums import ClaimSource, EpistemicStatus
from ally.firewall import hits as firewall_hits
from ally.retrieval import retrieval_timeout, unresolved_envelope

ENV_LIVE_WEB = "ALLY_LIVE_WEB"


class WebSearcher(Protocol):
    def search(self, human: HumanInput) -> list[InboundEnvelope]:
        """Return tagged web envelopes. Epistemic is unresolved until verified."""


class PageFetcher(Protocol):
    def fetch(self, url: str) -> InboundEnvelope:
        """Fetch one URL. Fetch is not verification."""


def live_web_enabled() -> bool:
    return os.environ.get(ENV_LIVE_WEB, "").strip().lower() in {"1", "true", "yes"}


def _host(url: str) -> str:
    return urlparse(url).netloc or "web"


class StaticSearcher:
    """Pytest / injected hits. Does not call the network."""

    def __init__(self, envelopes: list[InboundEnvelope]) -> None:
        self.envelopes = envelopes

    def search(self, human: HumanInput) -> list[InboundEnvelope]:
        del human
        return list(self.envelopes)


class HttpFetcher:
    def fetch(self, url: str) -> InboundEnvelope:
        try:
            response = httpx.get(
                url, follow_redirects=True, timeout=retrieval_timeout()
            )
            response.raise_for_status()
        except httpx.TimeoutException:
            return unresolved_envelope(
                citation=url,
                detail=f"timeout fetching {_host(url)}",
            )
        except httpx.HTTPError as exc:
            return unresolved_envelope(
                citation=url,
                detail=f"http error fetching {_host(url)}: {exc}",
            )
        text = " ".join(response.text.split())
        if firewall_hits(text):
            text = text[:400]
        return InboundEnvelope(
            source=ClaimSource.WEB,
            epistemic=EpistemicStatus.UNRESOLVED,
            citation=url,
            text=f"Fetched {_host(url)}: {text[:500]}",
        )


class DuckDuckGoSearcher:
    """Generic search. Conflicting secondary numbers stay unresolved."""

    def search(self, human: HumanInput) -> list[InboundEnvelope]:
        query = f"{human.brand_id} {human.task}"
        try:
            response = httpx.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": query,
                    "format": "json",
                    "no_html": "1",
                    "skip_disambig": "1",
                },
                timeout=retrieval_timeout(),
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException:
            return [
                unresolved_envelope(
                    citation="web search",
                    detail="timeout contacting DuckDuckGo",
                )
            ]
        except httpx.HTTPError as exc:
            return [
                unresolved_envelope(
                    citation="web search",
                    detail=f"http error contacting DuckDuckGo: {exc}",
                )
            ]
        except json.JSONDecodeError:
            return [
                unresolved_envelope(
                    citation="web search",
                    detail="malformed payload from DuckDuckGo",
                )
            ]
        if not isinstance(payload, dict):
            return [
                unresolved_envelope(
                    citation="web search",
                    detail="malformed payload from DuckDuckGo",
                )
            ]
        envelopes: list[InboundEnvelope] = []
        abstract = (payload.get("AbstractText") or "").strip()
        abstract_url = payload.get("AbstractURL") or ""
        if abstract:
            envelopes.append(
                InboundEnvelope(
                    source=ClaimSource.WEB,
                    epistemic=EpistemicStatus.UNRESOLVED,
                    citation=abstract_url or "DuckDuckGo abstract",
                    text=abstract[:800],
                )
            )
        for topic in payload.get("RelatedTopics") or []:
            if not isinstance(topic, dict):
                continue
            text = (topic.get("Text") or "").strip()
            url = topic.get("FirstURL") or "DuckDuckGo related"
            if text:
                envelopes.append(
                    InboundEnvelope(
                        source=ClaimSource.WEB,
                        epistemic=EpistemicStatus.UNRESOLVED,
                        citation=url,
                        text=text[:800],
                    )
                )
            if len(envelopes) >= 5:
                break
        return envelopes


def searcher_from_env() -> WebSearcher | None:
    if not live_web_enabled():
        return None
    return DuckDuckGoSearcher()
