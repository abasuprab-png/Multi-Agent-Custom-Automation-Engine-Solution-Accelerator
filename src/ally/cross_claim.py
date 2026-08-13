"""Cross-claim rules. GI-AE is one row in the registry, not a one-off in critique."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ally.contracts import Claim, CritiqueIssue
from ally.enums import CritiqueCode

_GI_QUALITATIVE = re.compile(
    r"gi (adverse events|aes?).{0,120}(comparable|mild|manageable|similar to placebo|not treatment[- ]limiting)"
    r"|(comparable|mild|manageable|similar to placebo|not treatment[- ]limiting).{0,120}gi (adverse events|aes?)",
    re.IGNORECASE,
)
_GI_QUANTITATIVE = re.compile(
    r"(discontinu(?:ation|ed).{0,80}gi|gi.{0,80}discontinu)"
    r"|gi (adverse events|aes?).{0,80}\d+(?:\.\d+)?\s*%",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TopicContradiction:
    """Qualitative minimizer vs quantified difference on the same topic."""

    rule_id: str
    qualitative: re.Pattern[str]
    quantitative: re.Pattern[str]
    message: str

    def check(self, claims: list[Claim]) -> list[CritiqueIssue]:
        qual = [claim for claim in claims if self.qualitative.search(claim.text)]
        quant = [claim for claim in claims if self.quantitative.search(claim.text)]
        if not (qual and quant):
            return []
        return [
            CritiqueIssue(
                code=CritiqueCode.CROSS_CLAIM,
                rule_id=self.rule_id,
                claim_ids=[claim.id for claim in qual + quant],
                message=(
                    f"{self.message} "
                    f"Qualitative claims: {[claim.id for claim in qual]}. "
                    f"Quantitative claims: {[claim.id for claim in quant]}. "
                    "Reconciliation must resolve this before lock."
                ),
            )
        ]


GI_AE_DISCONTINUATION = TopicContradiction(
    rule_id="XCLAIM-GI-AE",
    qualitative=_GI_QUALITATIVE,
    quantitative=_GI_QUANTITATIVE,
    message="GI-AE characterization contradicts GI-related discontinuation or rate difference.",
)

CROSS_CLAIM_RULES: tuple[TopicContradiction, ...] = (GI_AE_DISCONTINUATION,)


def check_cross_claims(claims: list[Claim]) -> list[CritiqueIssue]:
    issues: list[CritiqueIssue] = []
    for rule in CROSS_CLAIM_RULES:
        issues.extend(rule.check(claims))
    return issues
