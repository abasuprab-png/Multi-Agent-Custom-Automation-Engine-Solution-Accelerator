"""Estimand labeling and intensifier lint are blocking, not style notes."""

from ally.enums import CritiqueCode, EstimandBasis
from ally.fixtures import gi_ae_contradiction_input, happy_path_input
from ally.runtime import run_vertical_slice


def test_efficacy_percent_without_estimand_fails():
    session = run_vertical_slice(gi_ae_contradiction_input())
    estimand_issues = [
        issue for issue in session.critique.issues if issue.code is CritiqueCode.ESTIMAND
    ]
    assert estimand_issues
    texts = []
    for issue in estimand_issues:
        for claim_id in issue.claim_ids:
            claim = session.diagnosis.claim_by_id(claim_id)
            if claim is not None:
                texts.append(claim.text)
    assert any("16.2%" in text for text in texts)


def test_high_precision_without_a_number_fails():
    session = run_vertical_slice(gi_ae_contradiction_input())
    intensifiers = [
        issue
        for issue in session.critique.issues
        if issue.code is CritiqueCode.INTENSIFIER
    ]
    assert intensifiers
    assert any("high-precision" in issue.message for issue in intensifiers)


def test_happy_path_treatment_policy_estimand_is_accepted():
    session = run_vertical_slice(happy_path_input())
    assert any(
        claim.estimand is EstimandBasis.TREATMENT_POLICY
        for claim in session.diagnosis.claims
    )
    assert all(issue.code is not CritiqueCode.ESTIMAND for issue in session.critique.issues)
    assert all(
        issue.code is not CritiqueCode.INTENSIFIER for issue in session.critique.issues
    )
