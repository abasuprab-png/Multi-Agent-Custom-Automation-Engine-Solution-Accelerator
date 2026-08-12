"""Estimand labeling and intensifier lint are blocking, not style notes."""

from ally.enums import CritiqueCode, EstimandBasis
from ally.fixtures import gi_ae_contradiction_input, happy_path_input
from ally.runtime import run_vertical_slice


def test_efficacy_percent_without_estimand_fails():
    _, result = run_vertical_slice(gi_ae_contradiction_input())
    assert result.critique is not None
    estimand_issues = [
        issue for issue in result.critique.issues if issue.code is CritiqueCode.ESTIMAND
    ]
    assert estimand_issues
    assert any("16.2%" in (result.diagnosis.claim_by_id(cid).text if result.diagnosis and result.diagnosis.claim_by_id(cid) else "") for issue in estimand_issues for cid in issue.claim_ids)


def test_high_precision_without_a_number_fails():
    _, result = run_vertical_slice(gi_ae_contradiction_input())
    assert result.critique is not None
    intensifiers = [
        issue for issue in result.critique.issues if issue.code is CritiqueCode.INTENSIFIER
    ]
    assert intensifiers
    assert any("high-precision" in issue.message for issue in intensifiers)


def test_happy_path_treatment_policy_estimand_is_accepted():
    _, result = run_vertical_slice(happy_path_input())
    assert result.diagnosis is not None
    assert any(claim.estimand is EstimandBasis.TREATMENT_POLICY for claim in result.diagnosis.claims)
    assert result.critique is not None
    assert all(issue.code is not CritiqueCode.ESTIMAND for issue in result.critique.issues)
    assert all(issue.code is not CritiqueCode.INTENSIFIER for issue in result.critique.issues)
