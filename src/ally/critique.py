"""Self-critique tool. Admissibility, cross-claim, estimand, intensifier, genre."""

from __future__ import annotations

import re

from ally.contracts import (
    AllyMessageSpineCandidate,
    AllyStrategicDiagnosis,
    Claim,
    CritiqueIssue,
    CritiqueReport,
)
from ally.cross_claim import check_cross_claims
from ally.enums import ChecklistAnswer, CritiqueCode, EpistemicStatus, Genre
from ally.firewall import hits as firewall_hits
from ally.insight import critique_insight
from ally.knowledge import genre_lede_ok, query_canon

_EFFICACY_HINT = re.compile(
    r"\b(weight loss|efficac|reduction|responder|hba1c|a1c|placebo-adjusted|mean change)\b",
    re.IGNORECASE,
)
_PERCENT = re.compile(r"\b\d+(?:\.\d+)?\s*%")
_INTENSIFIERS = (
    "high-precision",
    "best-in-class",
    "unprecedented",
    "unparalleled",
    "most effective",
    "transformative",
    "world-class",
    "highest",
    "lowest",
)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def run_self_critique(diagnosis: AllyStrategicDiagnosis) -> CritiqueReport:
    """Highest-leverage gate. Runs before Human Strategic Lock, not instead of it."""
    issues: list[CritiqueIssue] = []
    issues.extend(_admissibility(diagnosis))
    issues.extend(check_cross_claims(diagnosis.claims))
    issues.extend(_estimand(diagnosis.claims))
    issues.extend(_intensifier(diagnosis.claims, diagnosis.spine_candidates))
    if diagnosis.insight is not None:
        issues.extend(_intensifier_in(diagnosis.insight.distinctive_solve))
        issues.extend(_intensifier_in(diagnosis.insight.unmet_need))
    issues.extend(_genre(diagnosis.spine_candidates))
    issues.extend(_firewall(diagnosis))
    issues.extend(critique_insight(diagnosis.insight))
    return CritiqueReport(issues=issues)


def _admissibility(diagnosis: AllyStrategicDiagnosis) -> list[CritiqueIssue]:
    adm1, adm2 = query_canon("ADM-1", "ADM-2")
    if not diagnosis.spine_candidates:
        return [
            CritiqueIssue(
                code=CritiqueCode.ADMISSIBILITY_CATALYST,
                rule_id=adm1.id,
                message="No spine candidate to run Admissibility against.",
            )
        ]
    issues: list[CritiqueIssue] = []
    for spine in diagnosis.spine_candidates:
        if spine.genre is Genre.STRATEGIC_COUNSEL:
            continue
        issues.extend(_spine_admissibility(spine, adm1.id, adm2.id))
    return issues


def _spine_admissibility(
    spine: AllyMessageSpineCandidate, adm1: str, adm2: str
) -> list[CritiqueIssue]:
    issues: list[CritiqueIssue] = []
    if (
        spine.catalyst_external is ChecklistAnswer.UNANSWERED
        or spine.catalyst_dated is ChecklistAnswer.UNANSWERED
    ):
        issues.append(
            CritiqueIssue(
                code=CritiqueCode.ADMISSIBILITY_CATALYST,
                rule_id=adm1,
                spine_id=spine.id,
                message=(
                    "Admissibility unanswered: catalyst_external and catalyst_dated "
                    "must be explicit yes/no. Unanswered is a no."
                ),
            )
        )
    elif not spine.catalyst_admissible():
        issues.append(
            CritiqueIssue(
                code=CritiqueCode.ADMISSIBILITY_CATALYST,
                rule_id=adm1,
                spine_id=spine.id,
                message=(
                    "Inadmissible: catalyst is not external and dated "
                    f"(external={spine.catalyst_external.value}, "
                    f"dated={spine.catalyst_dated.value}, date={spine.catalyst_date!r})."
                ),
            )
        )
    if spine.tension_market_held is ChecklistAnswer.UNANSWERED:
        issues.append(
            CritiqueIssue(
                code=CritiqueCode.ADMISSIBILITY_TENSION,
                rule_id=adm2,
                spine_id=spine.id,
                message=(
                    "Admissibility unanswered: tension_market_held must be explicit. "
                    "Unanswered is a no."
                ),
            )
        )
    elif not spine.tension_admissible():
        issues.append(
            CritiqueIssue(
                code=CritiqueCode.ADMISSIBILITY_TENSION,
                rule_id=adm2,
                spine_id=spine.id,
                message=(
                    "Inadmissible: tension is not market-held with an observable marker "
                    f"(held={spine.tension_market_held.value}, "
                    f"marker={spine.tension_observable_marker!r})."
                ),
            )
        )
    return issues


def _estimand(claims: list[Claim]) -> list[CritiqueIssue]:
    issues: list[CritiqueIssue] = []
    for claim in claims:
        if claim.epistemic is EpistemicStatus.UNRESOLVED:
            continue
        if (
            _PERCENT.search(claim.text)
            and _EFFICACY_HINT.search(claim.text)
            and claim.estimand is None
        ):
            issues.append(
                CritiqueIssue(
                    code=CritiqueCode.ESTIMAND,
                    rule_id="EST-1",
                    claim_ids=[claim.id],
                    message=(
                        "Efficacy percentage without estimand basis "
                        "(trial-product, treatment-policy, or treatment-regimen)."
                    ),
                )
            )
    return issues


def _intensifier(
    claims: list[Claim], spines: list[AllyMessageSpineCandidate]
) -> list[CritiqueIssue]:
    issues: list[CritiqueIssue] = []
    for claim in claims:
        issues.extend(_intensifier_in(claim.text, claim_ids=[claim.id]))
    for spine in spines:
        issues.extend(_intensifier_in(spine.lede, spine_id=spine.id))
    return issues


def _intensifier_in(
    text: str, *, claim_ids: list[str] | None = None, spine_id: str | None = None
) -> list[CritiqueIssue]:
    lowered = text.lower()
    issues: list[CritiqueIssue] = []
    for word in _INTENSIFIERS:
        if word not in lowered:
            continue
        sentence = _sentence_containing(text, word)
        if not _NUMBER.search(sentence):
            issues.append(
                CritiqueIssue(
                    code=CritiqueCode.INTENSIFIER,
                    rule_id="INT-1",
                    claim_ids=claim_ids or [],
                    spine_id=spine_id,
                    message=(
                        f"Intensifier '{word}' is not traceable to a cited number "
                        "in the same sentence."
                    ),
                )
            )
    return issues


def _sentence_containing(text: str, needle: str) -> str:
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if needle in sentence.lower():
            return sentence
    return text


def _genre(spines: list[AllyMessageSpineCandidate]) -> list[CritiqueIssue]:
    issues: list[CritiqueIssue] = []
    for spine in spines:
        ok, reason = genre_lede_ok(spine.lede, spine.genre)
        if not ok:
            issues.append(
                CritiqueIssue(
                    code=CritiqueCode.GENRE,
                    rule_id="GENRE-AR-1",
                    spine_id=spine.id,
                    message=reason,
                )
            )
    return issues


def _firewall(diagnosis: AllyStrategicDiagnosis) -> list[CritiqueIssue]:
    issues: list[CritiqueIssue] = []
    for claim in diagnosis.claims:
        hits = firewall_hits(claim.text)
        if hits:
            issues.append(
                CritiqueIssue(
                    code=CritiqueCode.VOCAB_FIREWALL,
                    rule_id="FW-1",
                    claim_ids=[claim.id],
                    message=f"Buyer-facing claim contains blocked vocabulary: {', '.join(hits)}",
                )
            )
    for spine in diagnosis.spine_candidates:
        hits = firewall_hits(spine.lede)
        if hits:
            issues.append(
                CritiqueIssue(
                    code=CritiqueCode.VOCAB_FIREWALL,
                    rule_id="FW-1",
                    spine_id=spine.id,
                    message=f"Spine lede contains blocked vocabulary: {', '.join(hits)}",
                )
            )
    return issues
