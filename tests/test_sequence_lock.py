"""Tests that the six-stage sequence is a lock, not a suggestion."""

import pytest
from pydantic import ValidationError

from ally.contracts import AgentHandoff
from ally.enums import ExecutionAgent, Stage
from ally.exceptions import LockGateError, SequenceLockError
from ally.fixtures import happy_path_input
from ally.lock import signed_lock
from ally.runtime import assert_transition, next_stage, run_vertical_slice


def test_six_stages_in_order():
    order = []
    stage: Stage | None = Stage.DISCOVERY
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
    with pytest.raises(SequenceLockError, match="evidence_reconciliation"):
        assert_transition(Stage.DISCOVERY, Stage.EVIDENCE_RECONCILIATION)


def test_cannot_enter_execution_from_discovery():
    with pytest.raises(SequenceLockError):
        assert_transition(Stage.DISCOVERY, Stage.EXECUTION)


def test_vertical_slice_stops_at_human_lock_not_execution():
    session = run_vertical_slice(happy_path_input())
    assert session.stage is Stage.HUMAN_STRATEGIC_LOCK
    assert session.lock is None
    with pytest.raises(LockGateError, match="lock signature"):
        session.enter_execution()


def test_lexie_handoff_without_lock_is_rejected_by_object_model():
    with pytest.raises(ValidationError):
        AgentHandoff(
            to_agent=ExecutionAgent.LEXIE,
            diagnosis_id="dx-1",
            claims=[],
        )
    with pytest.raises(ValidationError):
        AgentHandoff(
            to_agent=ExecutionAgent.RCC,
            diagnosis_id="dx-1",
            claims=[],
        )


def test_signed_lock_releases_execution():
    session = run_vertical_slice(happy_path_input())
    lock = signed_lock(
        session.diagnosis.digest(),
        "lead-b",
        closed_decision_ids=[
            point.id for point in session.diagnosis.open_decision_points
        ],
    )
    session.apply_lock(lock)
    handoff = session.enter_execution(to_agent="lexie")
    assert session.stage is Stage.EXECUTION
    assert handoff.lock.signed_by == "lead-b"
    assert handoff.lock.signature == lock.signature
    assert handoff.to_agent is ExecutionAgent.LEXIE
