"""Writer craft findings. Judgment only — never a deterministic gate.

Source: regulated-wire-editor doctrine + AP/exemplar library (Aug 16, 2026).
Deterministic enforcement stays in the claim pipeline (quarantine, ADM, estimand).
"""

from __future__ import annotations

from dataclasses import dataclass

COMPETITOR_TOKENS: tuple[str, ...] = (
    "wegovy",
    "ozempic",
    "mounjaro",
    "zepbound",
    "foundayo",
    "keytruda",
)

BANNED_SELF_DESCRIPTION: tuple[str, ...] = (
    "thrilled",
    "excited",
    "pleased",
    "transformative",
    "best-in-class",
    "world-class",
    "revolutionary",
    "game-changing",
    "groundbreaking",
    "paradigm shift",
    "high-precision",
)

_ANNOUNCEMENT_OF_ANNOUNCEMENT: tuple[str, ...] = (
    "previously announced",
    "announced the announcement",
    "was investigational and was not approved",
    "prior nda submission",
)


@dataclass(frozen=True)
class CraftFinding:
    """A communications-quality flag. `blocks` is always False."""

    rule_id: str
    message: str
    blocks: bool = False

    def __post_init__(self) -> None:
        if self.blocks:
            raise ValueError("Writer craft findings must not block")


def review_draft(text: str, *, brand_id: str = "") -> list[CraftFinding]:
    """Return findings for a Writer draft. Empty list is not a pass verdict."""
    findings: list[CraftFinding] = []
    lowered = text.lower()
    brand = brand_id.lower()
    findings.extend(_competitor_silence(lowered, brand))
    findings.extend(_draft_label(text, lowered))
    findings.extend(_news_peg(lowered))
    findings.extend(_banned_self_description(lowered))
    return findings


def _competitor_silence(lowered: str, brand: str) -> list[CraftFinding]:
    hits = [
        token
        for token in COMPETITOR_TOKENS
        if token in lowered and token not in brand
    ]
    if not hits:
        return []
    return [
        CraftFinding(
            rule_id="CRAFT-COMP-1",
            message=(
                "Competitor product named in outward copy: "
                + ", ".join(hits)
                + ". Competitor silence is the correct posture; comparisons route to Q&A."
            ),
        )
    ]


def _draft_label(text: str, lowered: str) -> list[CraftFinding]:
    unfinished = "[" in text or "draft" in lowered or "[confirm:" in lowered
    if "for immediate release" in lowered and unfinished:
        return [
            CraftFinding(
                rule_id="CRAFT-LABEL-1",
                message=(
                    "FOR IMMEDIATE RELEASE on an unfinished, bracketed, or unapproved draft. "
                    "Working drafts carry DRAFT plus the typed scenario genre."
                ),
            )
        ]
    return []


def _news_peg(lowered: str) -> list[CraftFinding]:
    if not any(marker in lowered for marker in _ANNOUNCEMENT_OF_ANNOUNCEMENT):
        return []
    return [
        CraftFinding(
            rule_id="CRAFT-PEG-1",
            message=(
                "Announcement-of-an-announcement or prior investigational status "
                "is being treated as news. A prior NDA or investigational line "
                "belongs in About, not the body."
            ),
        )
    ]


def _banned_self_description(lowered: str) -> list[CraftFinding]:
    hits = [word for word in BANNED_SELF_DESCRIPTION if word in lowered]
    if not hits:
        return []
    return [
        CraftFinding(
            rule_id="CRAFT-LEX-1",
            message=(
                "Banned self-description in Writer copy: "
                + ", ".join(hits)
                + ". Finding only; the claim pipeline is the gate."
            ),
        )
    ]
