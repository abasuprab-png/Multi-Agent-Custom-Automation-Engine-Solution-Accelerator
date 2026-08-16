"""Retrievable knowledge. Citability is the point; these are not prompt flavor."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ally.enums import EstimandBasis, Genre
from ally.exceptions import RefusalError

_COMPLETED_ACTION = (
    "has approved",
    "approves",
    "has granted marketing authorization",
    "has granted",
    "has authorized",
    "authorized",
    "has granted accelerated approval",
)

_NOT_COMPLETED = (
    "will approve",
    "expected to",
    "looks toward",
    "is beginning",
    "new chapter",
    "poised to",
    "on the horizon",
    "set to transform",
)


@dataclass(frozen=True)
class CanonRule:
    id: str
    title: str
    body: str


CANON: dict[str, CanonRule] = {
    "ADM-1": CanonRule(
        id="ADM-1",
        title="Catalyst must be external and dated",
        body=(
            "A message is admissible only if its catalyst is an external event "
            "(regulator, competitor, payer, guideline body, or similarly dated "
            "public act) and that event carries an explicit date. Internal "
            "ambition, brand calendars, and undated 'momentum' are not catalysts."
        ),
    ),
    "ADM-2": CanonRule(
        id="ADM-2",
        title="Tension must be market-held with an observable marker",
        body=(
            "A message is admissible only if the tension is already held in the "
            "market and can be pointed to with an observable marker (share shift, "
            "guideline language, formulary action, competitor claim, or equivalent). "
            "A tension that exists only inside the brand team is inadmissible."
        ),
    ),
}

ESTIMAND_LEXICON: dict[EstimandBasis, str] = {
    EstimandBasis.TRIAL_PRODUCT: (
        "Trial-product: the effect if all randomized patients had taken the "
        "investigational product as directed, typically after intercurrent-event "
        "handling that isolates pharmacological effect."
    ),
    EstimandBasis.TREATMENT_POLICY: (
        "Treatment-policy: the effect of the assigned treatment strategy regardless "
        "of adherence, discontinuation, or rescue, corresponding to ITT-like handling "
        "of intercurrent events."
    ),
    EstimandBasis.TREATMENT_REGIMEN: (
        "Treatment-regimen: the effect of a specified regimen that may include "
        "discontinuation rules or subsequent therapy as part of the strategy itself."
    ),
}

APPROVAL_RELEASE_LEDES: tuple[str, ...] = (
    "The FDA has approved semaglutide 2.4 mg for chronic weight management in adults with obesity.",
    "The European Commission has granted marketing authorization for donanemab for early symptomatic Alzheimer's disease.",
    "The FDA has approved a new indication for empagliflozin to reduce the risk of cardiovascular death in adults with heart failure.",
    "The MHRA has approved tirzepatide for weight management in adults with a BMI of 30 kg/m² or greater.",
    "The FDA has granted accelerated approval to tofersen for SOD1-ALS.",
)


def query_canon(*rule_ids: str) -> list[CanonRule]:
    """Return citable Canon rules. Unknown IDs are a refusal, not a paraphrase."""
    found: list[CanonRule] = []
    missing: list[str] = []
    for rule_id in rule_ids:
        rule = CANON.get(rule_id)
        if rule is None:
            missing.append(rule_id)
        else:
            found.append(rule)
    if missing:
        raise RefusalError(f"Unknown Canon rule ids: {', '.join(missing)}")
    return found


def first_sentence(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", stripped, maxsplit=1)
    return parts[0].strip()


def genre_lede_ok(lede: str, genre: Genre) -> tuple[bool, str]:
    """Genre convention is a checker, not a vibe. Approval releases are SVO completed action."""
    if genre != Genre.APPROVAL_RELEASE:
        return True, "non-approval genre: convention library not applied in this slice"
    sentence = first_sentence(lede)
    lowered = sentence.lower()
    if any(marker in lowered for marker in _NOT_COMPLETED):
        return False, "lede is atmospheric or prospective, not a completed regulatory action"
    if not any(verb in lowered for verb in _COMPLETED_ACTION):
        return False, "first sentence does not state a completed regulatory action in present perfect/present"
    has_subject = bool(
        re.match(
            r"^(the\s+)?(fda|ema|mhra|european commission|pmda|health canada)\b",
            lowered,
        )
        or re.search(r"\bhas approved\b|\bhas granted\b|\bapproves\b", lowered)
    )
    if not has_subject:
        return False, "first sentence is not subject-verb-object with a regulator or completed-action verb"
    return True, "completed regulatory action, present tense, SVO"
