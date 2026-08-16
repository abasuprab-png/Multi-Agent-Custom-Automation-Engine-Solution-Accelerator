"""Retrievable knowledge. Citability is the point; these are not prompt flavor."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ally.enums import EstimandBasis, Genre
from ally.exceptions import RefusalError

DOCS_DIR = Path(__file__).resolve().parent / "knowledge_docs"

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


@dataclass(frozen=True)
class GenreExample:
    genre: Genre
    tag: str
    lede: str
    path: str


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text.strip()
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text.strip()
    meta: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta, parts[2].strip()


def _load_canon() -> dict[str, CanonRule]:
    loaded: dict[str, CanonRule] = {}
    root = DOCS_DIR / "canon"
    if not root.is_dir():
        return loaded
    for path in sorted(root.glob("*.md")):
        meta, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
        rule_id = meta.get("id")
        title = meta.get("title")
        if not rule_id or not title or not body:
            continue
        loaded[rule_id] = CanonRule(id=rule_id, title=title, body=body)
    return loaded


def _load_genre_library() -> tuple[GenreExample, ...]:
    examples: list[GenreExample] = []
    root = DOCS_DIR / "genre"
    if not root.is_dir():
        return ()
    for path in sorted(root.glob("*.md")):
        meta, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
        raw_genre = meta.get("genre", Genre.APPROVAL_RELEASE.value)
        try:
            genre = Genre(raw_genre)
        except ValueError:
            continue
        if not body:
            continue
        examples.append(
            GenreExample(
                genre=genre,
                tag=meta.get("tag", path.stem),
                lede=body.splitlines()[0],
                path=str(path.relative_to(DOCS_DIR)),
            )
        )
    return tuple(examples)


_FALLBACK_CANON: dict[str, CanonRule] = {
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

CANON: dict[str, CanonRule] = {**_FALLBACK_CANON, **_load_canon()}

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

CANONICAL_APPROVAL_LEDE = (
    "[Company] today announced that the U.S. Food and Drug Administration (FDA) "
    "has approved [BRAND (generic, dose)] for [indication]."
)

APPROVAL_RELEASE_LEDES: tuple[str, ...] = (
    "The FDA has approved semaglutide 2.4 mg for chronic weight management in adults with obesity.",
    "The European Commission has granted marketing authorization for donanemab for early symptomatic Alzheimer's disease.",
    "The FDA has approved a new indication for empagliflozin to reduce the risk of cardiovascular death in adults with heart failure.",
    "The MHRA has approved tirzepatide for weight management in adults with a BMI of 30 kg/m² or greater.",
    "The FDA has granted accelerated approval to tofersen for SOD1-ALS.",
    (
        "Novo Nordisk today announced that the U.S. Food and Drug Administration "
        "(FDA) has approved oral semaglutide 25 mg for chronic weight management "
        "in adults with obesity."
    ),
    (
        "Eli Lilly and Company today announced that the U.S. Food and Drug "
        "Administration (FDA) has approved orforglipron for chronic weight "
        "management in adults with obesity."
    ),
)

GENRE_LIBRARY: tuple[GenreExample, ...] = _load_genre_library()
if GENRE_LIBRARY:
    APPROVAL_RELEASE_LEDES = tuple(
        example.lede
        for example in GENRE_LIBRARY
        if example.genre is Genre.APPROVAL_RELEASE
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


def query_genre(genre: Genre) -> list[GenreExample]:
    """Return curated examples for a genre. Empty is not a paraphrase of another genre."""
    return [example for example in GENRE_LIBRARY if example.genre is genre]


_ABBREVIATION = re.compile(
    r"\b(?:U\.S|U\.K|E\.U|D\.C|Inc|Ltd|Corp|vs|Dr|Prof|Mr|Ms|Mrs)\.$",
    re.IGNORECASE,
)


def first_sentence(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    for match in re.finditer(r"[.!?]\s+", stripped):
        candidate = stripped[: match.start() + 1]
        if _ABBREVIATION.search(candidate):
            continue
        return candidate.strip()
    return stripped


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
