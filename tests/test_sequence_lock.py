"""Tests that the six-stage sequence is a lock, not a suggestion."""

import pytest

from ally.contracts import AgentHandoff, HumanStrategicLock
from ally.enums import LockState, Stage
from ally.exceptions import LockGateError, SequenceLockError
from ally.fixtures import happy_path_input
from ally.runtime import AllySession, diagnosis_digest, next_stage, run_vertical_slice


def test_six_stages_in_order():
    order = []
    stage = Stage.DISCOVERY
    while stage is not None:
        order.append(stage)
        stage = next_stage(stage)
    assert [item.value for item in order] == [
        "discovery",
        "counsel",
        "structured_retrieval",
        "evidence_reconciliation",
        "human_strategic_lock",
        "execution",
    ]


def test_cannot_skip_to_reconciliation():
    session = AllySession(client_id="c", brand_id="b", lead_id="l")
    with pytest.raises(SequenceLockError, match="evidence_reconciliation"):
        session.advance_to(Stage.EVIDENCE_RECONCILIATION)


def test_cannot_enter_execution_from_discovery():
    session = AllySession(client_id="c", brand_id="b", lead_id="l")
    with pytest.raises(SequenceLockError):
        session.advance_to(Stage.EXECUTION)


def test_vertical_slice_stops_at_human_lock_not_execution():
    session, result = run_vertical_slice(happy_path_input())
    assert result.status == "awaiting_human_lock"
    assert result.stage is Stage.HUMAN_STRATEGIC_LOCK
    assert session.lock_state is LockState.AWAITING_SIGNATURE
    assert session.lock is None
    with pytest.raises(LockGateError, match="lock signature"):
        session.enter_execution()


def test_lexie_handoff_without_lock_is_rejected_by_object_model():
    with pytest.raises(ValueError, match="lock signature"):
        AgentHandoff(
            from_agent="ally",
            to_agent="lexie",
            diagnosis_id="dx-1",
            claims=[],
            lock=None,
        )
    with pytest.raises(ValueError, match="lock signature"):
        AgentHandoff(
            from_agent="ally",
            to_agent="rcc",
            diagnosis_id="dx-1",
            claims=[],
        )


def test_signed_lock_releases_execution():
    session, result = run_vertical_slice(happy_path_input())
    assert result.diagnosis is not None
    lock = HumanStrategicLock(
        diagnosis_digest=diagnosis_digest(result.diagnosis),
        signed_by="lead-b",
        signature="sig-lead-b",
        closed_decision_ids=[
            point.id for point in result.diagnosis.open_decision_points if point.blocking
        ],
    )
    session.apply_lock(lock)
    handoff = session.enter_execution(to_agent="lexie")
    assert session.stage is Stage.EXECUTION
    assert handoff.lock is not None
    assert handoff.lock.signature == "sig-lead-b"
    assert "lexie" == handoff.to_agent
