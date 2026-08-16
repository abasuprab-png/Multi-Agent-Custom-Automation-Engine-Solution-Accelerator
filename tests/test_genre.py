"""Genre convention is few-shot plus a checker. Atmosphere is not an approval lede."""

from ally.enums import CritiqueCode, Genre
from ally.fixtures import gi_ae_contradiction_input, happy_path_input
from ally.knowledge import APPROVAL_RELEASE_LEDES, genre_lede_ok
from ally.runtime import run_vertical_slice


def test_curated_approval_ledes_pass():
    assert len(APPROVAL_RELEASE_LEDES) >= 5
    for lede in APPROVAL_RELEASE_LEDES:
        ok, reason = genre_lede_ok(lede, Genre.APPROVAL_RELEASE)
        assert ok, f"{lede!r} failed: {reason}"


def test_atmospheric_lede_fails_genre_check():
    ok, reason = genre_lede_ok(
        "A new chapter in obesity care is beginning as patients look toward next-generation options.",
        Genre.APPROVAL_RELEASE,
    )
    assert not ok
    assert "completed regulatory action" in reason or "atmospheric" in reason


def test_planted_spine_fails_genre_in_slice():
    session = run_vertical_slice(gi_ae_contradiction_input())
    assert any(issue.code is CritiqueCode.GENRE for issue in session.critique.issues)


def test_happy_path_lede_passes_genre():
    session = run_vertical_slice(happy_path_input())
    assert all(issue.code is not CritiqueCode.GENRE for issue in session.critique.issues)
