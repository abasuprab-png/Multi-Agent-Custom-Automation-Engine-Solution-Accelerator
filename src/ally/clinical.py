"""Live ClinicalTrials.gov and openFDA. Primary data over press paraphrase."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from ally.contracts import HumanInput, InboundEnvelope
from ally.enums import ClaimSource, EpistemicStatus, EstimandBasis
from ally.retrieval import (
    RetrievalClosedError,
    RetrievalQuery,
    StructuredRetriever,
    percents_in,
    retrieval_timeout,
    unresolved_envelope,
)

ENV_LIVE_RETRIEVAL = "ALLY_LIVE_RETRIEVAL"
CTGOV_STUDY = "https://clinicaltrials.gov/api/v2/studies/{nct_id}"
OPENFDA_LABEL = "https://api.fda.gov/drug/label.json"


def live_retrieval_enabled() -> bool:
    return os.environ.get(ENV_LIVE_RETRIEVAL, "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _estimand_from(text: str) -> EstimandBasis | None:
    lowered = text.lower()
    if "treatment-policy" in lowered or "treatment policy" in lowered or "intent-to-treat" in lowered or "itt" in lowered:
        return EstimandBasis.TREATMENT_POLICY
    if "trial-product" in lowered or "trial product" in lowered:
        return EstimandBasis.TRIAL_PRODUCT
    if "treatment-regimen" in lowered or "treatment regimen" in lowered:
        return EstimandBasis.TREATMENT_REGIMEN
    return None


def _get_json(url: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        response = httpx.get(
            url, params=params, timeout=retrieval_timeout(), follow_redirects=True
        )
    except httpx.TimeoutException as exc:
        raise RetrievalClosedError(f"timeout contacting {url}") from exc
    except httpx.HTTPError as exc:
        raise RetrievalClosedError(f"http error contacting {url}: {exc}") from exc
    try:
        if response.status_code >= 400:
            raise RetrievalClosedError(f"http {response.status_code} contacting {url}")
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise RetrievalClosedError(f"malformed payload from {url}") from exc
    except RetrievalClosedError:
        raise
    except Exception as exc:
        raise RetrievalClosedError(f"malformed payload from {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RetrievalClosedError(f"malformed payload from {url}")
    return payload


def _walk(node: Any) -> list[str]:
    texts: list[str] = []
    if isinstance(node, str):
        if node.strip():
            texts.append(node.strip())
        return texts
    if isinstance(node, dict):
        for value in node.values():
            texts.extend(_walk(value))
        return texts
    if isinstance(node, list):
        for item in node:
            texts.extend(_walk(item))
    return texts


class ClinicalTrialsGov:
    """https://clinicaltrials.gov/api/v2 — already-tagged primary envelopes."""

    def fetch(self, query: RetrievalQuery) -> list[InboundEnvelope]:
        if not query.nct_id:
            return []
        citation = f"ClinicalTrials.gov {query.nct_id}"
        try:
            payload = _get_json(CTGOV_STUDY.format(nct_id=query.nct_id))
            study = payload.get("protocolSection") or payload
            if not isinstance(study, dict):
                raise RetrievalClosedError("malformed ClinicalTrials.gov study")
            results = payload.get("resultsSection") or {}
            if results and not isinstance(results, dict):
                raise RetrievalClosedError("malformed ClinicalTrials.gov results")
            title = (
                ((study.get("identificationModule") or {}).get("officialTitle"))
                or ((study.get("identificationModule") or {}).get("briefTitle"))
                or query.nct_id
            )
            outcomes = results.get("outcomeMeasuresModule") or {}
            blobs = _walk(outcomes) or _walk((study.get("outcomesModule") or {}))
            text_block = " ".join(blobs)[:1200] or title
            estimand = _estimand_from(text_block)
            anchors = sorted(percents_in(text_block))
            return [
                InboundEnvelope(
                    source=ClaimSource.WEB,
                    epistemic=EpistemicStatus.VERIFIED,
                    citation=citation,
                    estimand=estimand,
                    numeric_anchors=anchors,
                    text=f"{title}. {text_block}"[:900],
                )
            ]
        except RetrievalClosedError as exc:
            return [unresolved_envelope(citation=citation, detail=str(exc))]


class OpenFdaLabel:
    """FDA label snippets. Competitive landscape is not stored here."""

    def fetch(self, query: RetrievalQuery) -> list[InboundEnvelope]:
        brand = (query.brand_id or "").strip()
        if not brand:
            return []
        citation = f"openFDA label {brand}"
        try:
            payload = _get_json(
                OPENFDA_LABEL,
                params={"search": f'openfda.brand_name:"{brand}"', "limit": "1"},
            )
            results = payload.get("results") or []
            if not results:
                return [
                    unresolved_envelope(
                        citation=citation,
                        detail="openFDA returned no label payload",
                    )
                ]
            label = results[0]
            if not isinstance(label, dict):
                raise RetrievalClosedError("malformed openFDA label")
            indications = " ".join(label.get("indications_and_usage") or [])
            if not indications:
                return [
                    unresolved_envelope(
                        citation=citation,
                        detail="openFDA label had no indications_and_usage",
                    )
                ]
            return [
                InboundEnvelope(
                    source=ClaimSource.WEB,
                    epistemic=EpistemicStatus.VERIFIED,
                    citation=citation,
                    text=indications[:800],
                )
            ]
        except RetrievalClosedError as exc:
            return [unresolved_envelope(citation=citation, detail=str(exc))]


class PrimaryRegulatoryRetriever:
    """ClinicalTrials.gov first, openFDA second. Press paraphrase is not the source of record."""

    def __init__(
        self,
        *,
        trials: ClinicalTrialsGov | None = None,
        labels: OpenFdaLabel | None = None,
    ) -> None:
        self.trials = trials or ClinicalTrialsGov()
        self.labels = labels or OpenFdaLabel()

    def fetch(self, query: RetrievalQuery) -> list[InboundEnvelope]:
        found: list[InboundEnvelope] = []
        try:
            found.extend(self.trials.fetch(query))
        except Exception as exc:
            found.append(
                unresolved_envelope(
                    citation=f"ClinicalTrials.gov {query.nct_id or 'unknown'}",
                    detail=f"timeout or malformed payload: {exc}",
                )
            )
        try:
            found.extend(self.labels.fetch(query))
        except Exception as exc:
            found.append(
                unresolved_envelope(
                    citation=f"openFDA {query.brand_id or 'unknown'}",
                    detail=f"timeout or malformed payload: {exc}",
                )
            )
        return found


def retriever_from_env() -> StructuredRetriever | None:
    if not live_retrieval_enabled():
        return None
    return PrimaryRegulatoryRetriever()


def retrieval_query_from(human: HumanInput) -> RetrievalQuery:
    return RetrievalQuery(brand_id=human.brand_id, task=human.task, nct_id=human.nct_id)
