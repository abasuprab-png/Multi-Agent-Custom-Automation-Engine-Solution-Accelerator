"""Primary clinical/regulatory retrieval. Press paraphrase is not the source of record."""

from __future__ import annotations

import os
import re
from typing import Protocol

from pydantic import BaseModel

from ally.contracts import Claim, InboundEnvelope, QuarantineRecord
from ally.enums import ClaimSource, EpistemicStatus, EstimandBasis, QuarantineReason

_PERCENT = re.compile(r"\b\d+(?:\.\d+)?\s*%")
ENV_RETRIEVAL_TIMEOUT = "ALLY_RETRIEVAL_TIMEOUT"
DEFAULT_RETRIEVAL_TIMEOUT = 8.0


class RetrievalClosedError(Exception):
    """Timeout or malformed live retrieval. Callers must fail closed."""


class RetrievalQuery(BaseModel):
    brand_id: str
    task: str
    nct_id: str | None = None


class StructuredRetriever(Protocol):
    def fetch(self, query: RetrievalQuery) -> list[InboundEnvelope]:
        """Return already-tagged primary envelopes. Never untagged paraphrase."""


def retrieval_timeout() -> float:
    raw = os.environ.get(ENV_RETRIEVAL_TIMEOUT, "").strip()
    if not raw:
        return DEFAULT_RETRIEVAL_TIMEOUT
    try:
        return max(0.1, float(raw))
    except ValueError:
        return DEFAULT_RETRIEVAL_TIMEOUT


def unresolved_envelope(*, citation: str, detail: str) -> InboundEnvelope:
    """Fail closed: missing live data is unresolved, not verified and not a crash."""
    return InboundEnvelope(
        source=ClaimSource.WEB,
        epistemic=EpistemicStatus.UNRESOLVED,
        citation=citation,
        text=f"epistemic: unresolved — {detail}",
    )


def percents_in(text: str, anchors: list[str] | None = None) -> set[str]:
    found = {match.group(0).replace(" ", "") for match in _PERCENT.finditer(text)}
    if anchors:
        found.update(anchor.replace(" ", "") for anchor in anchors)
    return found


def prefer_primary(
    secondary: list[Claim], primary: list[Claim]
) -> tuple[list[Claim], list[QuarantineRecord]]:
    """Drop estimand-less secondaries whose number is already on a primary record."""
    covered: set[str] = set()
    for claim in primary:
        if claim.estimand is not None:
            covered |= percents_in(claim.text, claim.numeric_anchors)
    kept: list[Claim] = []
    held: list[QuarantineRecord] = []
    for claim in secondary:
        keys = percents_in(claim.text, claim.numeric_anchors)
        if claim.estimand is None and keys & covered:
            held.append(
                QuarantineRecord.hold_claim(
                    claim,
                    QuarantineReason.SECONDARY_SUPERSEDED,
                    "Primary clinical/regulatory record supplies this number with an estimand. "
                    "Press-release paraphrase was held.",
                )
            )
        else:
            kept.append(claim)
    return kept, held


class ClinicalTrialsFixture:
    """Stand-in for ClinicalTrials.gov. Swap for a live client without changing the pipeline."""

    def __init__(self, records: list[InboundEnvelope]) -> None:
        self.records = records

    def fetch(self, query: RetrievalQuery) -> list[InboundEnvelope]:
        return list(self.records)


def redefine1_weight_loss_record() -> InboundEnvelope:
    return InboundEnvelope(
        source=ClaimSource.WEB,
        epistemic=EpistemicStatus.VERIFIED,
        citation="ClinicalTrials.gov NCT05668715 results",
        estimand=EstimandBasis.TREATMENT_POLICY,
        numeric_anchors=["16.2%", "2.4%"],
        text=(
            "Treatment-policy estimand: mean body-weight reduction was 16.2% "
            "with exampletide versus 2.4% with placebo."
        ),
    )
