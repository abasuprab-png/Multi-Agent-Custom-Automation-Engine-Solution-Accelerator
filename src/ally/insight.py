"""CCO strategic insight. Method is code. Competitive landscape is not baked in."""

from __future__ import annotations

from typing import Any

from ally.contracts import CritiqueIssue, StrategicInsight
from ally.enums import ChecklistAnswer, CritiqueCode, EpistemicStatus

_COMPARATIVE = (
    "better than anyone",
    "better than anyone else",
    "best-in-class",
    "best in class",
    "number one",
    "unmatched",
    "only product that",
    "wins the class",
)

_TRUST_MEDIATORS = (
    "hcp",
    "physician",
    "endocrin",
    "specialist",
    "guideline",
    "payer",
    "pbm",
    "formulary",
    "regulator",
    "fda",
    "ema",
    "advocacy",
    "employer",
    "kol",
    "pharmacist",
    "obesity medicine",
    "prescrib",
)


def insight_from_notes(notes: Any) -> StrategicInsight | None:
    """Lift a typed insight from counsel notes. Empty fields are not an insight."""
    unmet = str(getattr(notes, "unmet_need", "") or "").strip()
    solve = str(getattr(notes, "distinctive_solve", "") or "").strip()
    space = str(getattr(notes, "white_space", "") or "").strip()
    trust = str(getattr(notes, "trust_dynamic", "") or "").strip()
    influencers = [
        item.strip()
        for item in list(getattr(notes, "primary_influencers", None) or [])
        if str(item).strip()
    ]
    if not (unmet and solve and space and trust and influencers):
        return None
    consumer = str(getattr(notes, "consumer_pressure", "") or "").strip() or None
    return StrategicInsight(
        unmet_need=unmet,
        distinctive_solve=solve,
        white_space=space,
        primary_influencers=influencers,
        trust_dynamic=trust,
        consumer_pressure=consumer,
        epistemic=EpistemicStatus.INFERRED,
    )


def critique_insight(insight: StrategicInsight | None) -> list[CritiqueIssue]:
    """SI-1..SI-5. Missing or puffery insight cannot reach writers unsigned."""
    if insight is None:
        return [
            CritiqueIssue(
                code=CritiqueCode.STRATEGIC_INSIGHT,
                rule_id="SI-5",
                message=(
                    "No strategic insight. Name the unmet need, the distinctive solve, "
                    "the influencer white space, and the trust dynamic that mediates sales."
                ),
            )
        ]
    issues: list[CritiqueIssue] = []
    if not insight.unmet_need.strip():
        issues.append(
            CritiqueIssue(
                code=CritiqueCode.STRATEGIC_INSIGHT,
                rule_id="SI-1",
                message=(
                    "Unmet need is missing. A CCO insight starts from an external "
                    "patient, clinician, or system need — not brand ambition."
                ),
            )
        )
    if not insight.distinctive_solve.strip():
        issues.append(
            CritiqueIssue(
                code=CritiqueCode.STRATEGIC_INSIGHT,
                rule_id="SI-2",
                message=(
                    "Distinctive solve is missing. Say what the product does that "
                    "addresses the unmet need. Do not substitute share rhetoric."
                ),
            )
        )
    else:
        lowered = insight.distinctive_solve.lower()
        if any(phrase in lowered for phrase in _COMPARATIVE):
            if insight.comparative_evidenced is not ChecklistAnswer.YES:
                issues.append(
                    CritiqueIssue(
                        code=CritiqueCode.STRATEGIC_INSIGHT,
                        rule_id="SI-2",
                        message=(
                            "Comparative 'better than anyone' language is not evidenced. "
                            "Competitive landscape is live retrieval only; unanswered "
                            "comparative_evidenced is a no."
                        ),
                    )
                )
    if not insight.white_space.strip() or not insight.primary_influencers:
        issues.append(
            CritiqueIssue(
                code=CritiqueCode.STRATEGIC_INSIGHT,
                rule_id="SI-3",
                message=(
                    "White space must live in the mind of named primary influencers, "
                    "not as a company aspiration."
                ),
            )
        )
    if insight.primary_influencers and not _has_trust_mediator(insight.primary_influencers):
        issues.append(
            CritiqueIssue(
                code=CritiqueCode.STRATEGIC_INSIGHT,
                rule_id="SI-4",
                message=(
                    "Primary influencers must include a trust mediator "
                    "(HCP, guideline, payer, regulator, advocacy, employer). "
                    "Consumer demand does not replace the people who mediate "
                    "prescription, coverage, and trust."
                ),
            )
        )
    if not insight.trust_dynamic.strip():
        issues.append(
            CritiqueIssue(
                code=CritiqueCode.STRATEGIC_INSIGHT,
                rule_id="SI-5",
                message=(
                    "Trust dynamic is missing. Name how those influencers turn "
                    "belief into a prescribed, covered, chosen therapy."
                ),
            )
        )
    return issues


def _has_trust_mediator(influencers: list[str]) -> bool:
    blob = " ".join(influencers).lower()
    return any(marker in blob for marker in _TRUST_MEDIATORS)
