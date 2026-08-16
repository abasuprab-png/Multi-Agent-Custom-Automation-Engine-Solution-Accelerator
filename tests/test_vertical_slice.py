"""End-to-end vertical slice: planted defects cannot reach execution."""

import pytest

from ally.contracts import HumanStrategicLock
from ally.enums import CritiqueCode, ExecutionAgent, Stage
from ally.exceptions import LockGateError
from ally.fixtures import gi_ae_contradiction_input, happy_path_input
from ally.lock import signed_lock
from ally.runtime import run_vertical_slice


def test_planted_draft_hits_all_five_forces():
    session = run_vertical_slice(gi_ae_contradiction_input())
    assert session.stage is Stage.HUMAN_STRATEGIC_LOCK
    assert session.lock is None

    codes = {issue.code for issue in session.critique.issues}
    assert CritiqueCode.ADMISSIBILITY_CATALYST in codes
    assert CritiqueCode.ADMISSIBILITY_TENSION in codes
    assert CritiqueCode.CROSS_CLAIM in codes
    assert CritiqueCode.GENRE in codes
    assert CritiqueCode.ESTIMAND in codes
    assert CritiqueCode.INTENSIFIER in codes
    assert CritiqueCode.STRATEGIC_INSIGHT in codes

    assert session.quarantine
    assert any(
        item.label == "monotherapy-arm-figures"
        for item in session.diagnosis.open_verification
    )

    with pytest.raises(LockGateError):
        session.enter_execution()


def test_lock_bound_to_wrong_digest_is_rejected():
    session = run_vertical_slice(happy_path_input())
    with pytest.raises(LockGateError, match="diagnosis_digest"):
        session.apply_lock(
            HumanStrategicLock(
                diagnosis_digest="0" * 64,
                signed_by="lead-b",
                signature="sig",
            )
        )


def test_lock_cannot_skip_blocking_decisions_on_the_planted_case():
    session = run_vertical_slice(gi_ae_contradiction_input())
    with pytest.raises(LockGateError, match="blocking decision"):
        session.apply_lock(
            signed_lock(session.diagnosis.digest(), "lead-a", closed_decision_ids=[])
        )


def test_human_can_close_planted_decisions_and_release_execution():
    session = run_vertical_slice(gi_ae_contradiction_input())
    lock = signed_lock(
        session.diagnosis.digest(),
        "lead-a",
        closed_decision_ids=[
            point.id for point in session.diagnosis.open_decision_points
        ],
    )
    session.apply_lock(lock)
    handoff = session.enter_execution(to_agent="rcc")
    assert handoff.to_agent is ExecutionAgent.RCC
    assert "monotherapy-arm-figures" in handoff.unresolved or any(
        "monotherapy" in item for item in handoff.unresolved
    )


def test_happy_path_critique_passes():
    session = run_vertical_slice(happy_path_input())
    assert session.critique.passed
    assert session.stage is Stage.HUMAN_STRATEGIC_LOCK
