"""End-to-end vertical slice: planted defects cannot reach execution."""

import pytest

from ally.contracts import HumanStrategicLock
from ally.enums import CritiqueCode, LockState, Stage
from ally.exceptions import LockGateError
from ally.fixtures import gi_ae_contradiction_input, happy_path_input
from ally.runtime import diagnosis_digest, run_vertical_slice


def test_planted_draft_hits_all_five_forces():
    session, result = run_vertical_slice(gi_ae_contradiction_input())
    assert result.handoff is not None
    assert result.stage is Stage.HUMAN_STRATEGIC_LOCK
    assert session.lock_state is LockState.AWAITING_SIGNATURE

    codes = {issue.code for issue in result.critique.blocking}  # type: ignore[union-attr]
    assert CritiqueCode.ADMISSIBILITY_CATALYST in codes
    assert CritiqueCode.ADMISSIBILITY_TENSION in codes
    assert CritiqueCode.CROSS_CLAIM in codes
    assert CritiqueCode.GENRE in codes
    assert CritiqueCode.ESTIMAND in codes
    assert CritiqueCode.INTENSIFIER in codes

    assert result.quarantine
    assert result.diagnosis is not None
    assert any(
        item.label == "monotherapy-arm-figures"
        for item in result.diagnosis.open_verification
    )

    with pytest.raises(LockGateError):
        session.enter_execution()


def test_lock_bound_to_wrong_digest_is_rejected():
    session, result = run_vertical_slice(happy_path_input())
    assert result.diagnosis is not None
    with pytest.raises(LockGateError, match="diagnosis_digest"):
        session.apply_lock(
            HumanStrategicLock(
                diagnosis_digest="0" * 64,
                signed_by="lead-b",
                signature="sig",
            )
        )


def test_lock_cannot_skip_blocking_decisions_on_the_planted_case():
    session, result = run_vertical_slice(gi_ae_contradiction_input())
    assert result.diagnosis is not None
    with pytest.raises(LockGateError, match="blocking decision"):
        session.apply_lock(
            HumanStrategicLock(
                diagnosis_digest=diagnosis_digest(result.diagnosis),
                signed_by="lead-a",
                signature="sig",
                closed_decision_ids=[],
            )
        )


def test_human_can_close_planted_decisions_and_release_execution():
    session, result = run_vertical_slice(gi_ae_contradiction_input())
    assert result.diagnosis is not None
    lock = HumanStrategicLock(
        diagnosis_digest=diagnosis_digest(result.diagnosis),
        signed_by="lead-a",
        signature="override-sig",
        closed_decision_ids=[
            point.id for point in result.diagnosis.open_decision_points if point.blocking
        ],
    )
    session.apply_lock(lock)
    handoff = session.enter_execution(to_agent="rcc")
    assert handoff.to_agent == "rcc"
    assert handoff.lock is not None
    assert "monotherapy-arm-figures" in handoff.unresolved or any(
        "monotherapy" in item for item in handoff.unresolved
    )


def test_happy_path_critique_passes():
    _, result = run_vertical_slice(happy_path_input())
    assert result.critique is not None
    assert result.critique.passed
    assert result.status == "awaiting_human_lock"
