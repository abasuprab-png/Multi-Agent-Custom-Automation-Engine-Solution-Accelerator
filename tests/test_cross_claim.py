"""Cross-claim consistency. The planted GI-AE / discontinuation contradiction cannot pass."""

from ally.contracts import Claim
from ally.cross_claim import check_cross_claims
from ally.enums import ClaimSource, CritiqueCode, EpistemicStatus, QuarantineReason, Stage
from ally.fixtures import gi_ae_contradiction_input, happy_path_input
from ally.runtime import run_vertical_slice


def test_gi_ae_discontinuation_contradiction_is_caught_and_held():
    session = run_vertical_slice(gi_ae_contradiction_input())
    cross = [
        issue for issue in session.critique.issues if issue.code is CritiqueCode.CROSS_CLAIM
    ]
    assert cross, "reconciliation must flag the GI-AE / discontinuation contradiction"
    assert any("not treatment-limiting" in record.text for record in session.quarantine)
    assert any(record.reason is QuarantineReason.CROSS_CLAIM for record in session.quarantine)
    remaining = " ".join(claim.text for claim in session.diagnosis.claims)
    assert "not treatment-limiting" not in remaining
    assert "Discontinuation due to GI" in remaining
    assert session.stage is Stage.HUMAN_STRATEGIC_LOCK
    assert "close out" in session.handoff.summary.lower() or "lock" in session.handoff.summary.lower()


def test_inferred_spin_does_not_become_a_downstream_fact():
    session = run_vertical_slice(gi_ae_contradiction_input())
    inferred = [
        claim
        for claim in session.diagnosis.claims
        if claim.epistemic is EpistemicStatus.INFERRED
    ]
    assert all("comparable to placebo" not in claim.text for claim in inferred)


def test_happy_path_has_no_cross_claim_failure():
    session = run_vertical_slice(happy_path_input())
    assert all(
        issue.code is not CritiqueCode.CROSS_CLAIM for issue in session.critique.issues
    )


def test_qualitative_gi_vs_rate_difference_is_enough():
    issues = check_cross_claims(
        [
            Claim(
                text="GI adverse events were comparable to placebo.",
                source=ClaimSource.AGENT,
                epistemic=EpistemicStatus.INFERRED,
            ),
            Claim(
                text="GI adverse events occurred in 80% versus 40% with placebo.",
                source=ClaimSource.WEB,
                epistemic=EpistemicStatus.VERIFIED,
            ),
        ]
    )
    assert issues
    assert issues[0].rule_id == "XCLAIM-GI-AE"
