"""Cross-claim consistency. The planted GI-AE / discontinuation contradiction cannot pass."""

from ally.enums import CritiqueCode, EpistemicStatus, QuarantineReason
from ally.fixtures import gi_ae_contradiction_input, happy_path_input
from ally.runtime import run_vertical_slice


def test_gi_ae_discontinuation_contradiction_is_caught_and_held():
    session, result = run_vertical_slice(gi_ae_contradiction_input())
    assert result.critique is not None
    cross = [issue for issue in result.critique.issues if issue.code is CritiqueCode.CROSS_CLAIM]
    assert cross, "reconciliation must flag the GI-AE / discontinuation contradiction"
    assert any("not treatment-limiting" in record.text for record in session.quarantine)
    assert any(record.reason is QuarantineReason.CROSS_CLAIM for record in session.quarantine)
    assert result.diagnosis is not None
    remaining = " ".join(claim.text for claim in result.diagnosis.claims)
    assert "not treatment-limiting" not in remaining
    assert "Discontinuation due to GI" in remaining
    assert result.status == "awaiting_human_lock"
    assert result.handoff is not None
    assert "close out" in result.handoff.summary.lower() or "lock" in result.handoff.summary.lower()


def test_inferred_spin_does_not_become_a_downstream_fact():
    _, result = run_vertical_slice(gi_ae_contradiction_input())
    assert result.diagnosis is not None
    inferred = [
        claim for claim in result.diagnosis.claims if claim.epistemic is EpistemicStatus.INFERRED
    ]
    assert all("comparable to placebo" not in claim.text for claim in inferred)


def test_happy_path_has_no_cross_claim_failure():
    _, result = run_vertical_slice(happy_path_input())
    assert result.critique is not None
    assert all(issue.code is not CritiqueCode.CROSS_CLAIM for issue in result.critique.issues)
