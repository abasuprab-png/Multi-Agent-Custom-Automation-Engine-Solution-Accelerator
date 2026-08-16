"""Writer craft findings never block. The stale AP 'more than/over' rule is gone."""

from ally.enums import Genre
from ally.knowledge import CANONICAL_APPROVAL_LEDE, genre_lede_ok
from ally.writer import review_draft


def test_findings_never_block():
    findings = review_draft(
        "FOR IMMEDIATE RELEASE\nDRAFT\nPatients were thrilled versus Wegovy."
    )
    assert findings
    assert all(finding.blocks is False for finding in findings)


def test_competitor_silence_is_a_finding():
    findings = review_draft(
        "The new option is an alternative to Wegovy for chronic weight management.",
        brand_id="cagrisema",
    )
    assert any(finding.rule_id == "CRAFT-COMP-1" for finding in findings)


def test_own_brand_name_is_not_a_competitor_hit():
    findings = review_draft(
        "Wegovy is approved for chronic weight management.",
        brand_id="wegovy",
    )
    assert all(finding.rule_id != "CRAFT-COMP-1" for finding in findings)


def test_immediate_release_on_bracketed_draft_is_a_finding():
    findings = review_draft(
        "FOR IMMEDIATE RELEASE\nThe FDA has approved [BRAND] for [indication]."
    )
    assert any(finding.rule_id == "CRAFT-LABEL-1" for finding in findings)


def test_more_than_and_over_are_not_findings():
    findings = review_draft(
        "Patients lost more than 20% of body weight. Others lost over 15%."
    )
    assert findings == []


def test_company_announced_lede_matches_canonical_shape():
    assert "today announced" in CANONICAL_APPROVAL_LEDE
    ok, reason = genre_lede_ok(
        "Novo Nordisk today announced that the U.S. Food and Drug Administration "
        "(FDA) has approved oral semaglutide 25 mg for chronic weight management "
        "in adults with obesity.",
        Genre.APPROVAL_RELEASE,
    )
    assert ok, reason
