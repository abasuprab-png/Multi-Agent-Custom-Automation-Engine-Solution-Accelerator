"""Outside-in discovery. Search and fetch are ports; hits are never ground truth."""

from __future__ import annotations

import os
from typing import Protocol
from urllib.parse import urlparse

from ally.contracts import HumanInput, InboundEnvelope
from ally.enums import ClaimSource, EpistemicStatus
from ally.firewall import hits as firewall_hits

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
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required for live fetch") from exc
        response = httpx.get(url, follow_redirects=True, timeout=20.0)
        response.raise_for_status()
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
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required for live web search") from exc
        query = f"{human.brand_id} {human.task}"
        response = httpx.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            timeout=20.0,
        )
        response.raise_for_status()
        payload = response.json()
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
