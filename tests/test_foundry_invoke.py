"""Foundry Invocations must stop at Human Strategic Lock and emit typed objects."""

from ally.contracts import HumanStrategicLock
from ally.enums import CritiqueCode, ExecutionAgent, Stage
from ally.fixtures import gi_ae_contradiction_input, happy_path_input
from ally.foundry import AllyInvokeRequest, InvokeOp, SessionStore, handle_invoke


def test_start_stops_at_lock_interrupt_and_does_not_emit_agent_handoff():
    store = SessionStore()
    response = handle_invoke(
        AllyInvokeRequest(op=InvokeOp.START, human=gi_ae_contradiction_input()),
        store,
    )
    assert response.error is None
    assert response.interrupt is True
    assert response.stage is Stage.HUMAN_STRATEGIC_LOCK
    assert response.handoff is not None
    assert response.agent_handoff is None
    assert response.diagnosis_digest == response.handoff.diagnosis.digest()
    codes = {issue.code for issue in response.handoff.critique.issues}
    assert CritiqueCode.CROSS_CLAIM in codes
    assert CritiqueCode.ADMISSIBILITY_CATALYST in codes
    assert CritiqueCode.GENRE in codes


def test_enter_execution_without_lock_is_an_interrupt_error_not_a_handoff():
    store = SessionStore()
    started = handle_invoke(
        AllyInvokeRequest(op=InvokeOp.START, human=gi_ae_contradiction_input()),
        store,
    )
    response = handle_invoke(
        AllyInvokeRequest(op=InvokeOp.ENTER_EXECUTION, session_id=started.session_id),
        store,
    )
    assert response.agent_handoff is None
    assert response.interrupt is True
    assert response.error_type == "LockGateError"
    assert response.stage is Stage.HUMAN_STRATEGIC_LOCK


def test_apply_lock_does_not_auto_enter_execution():
    store = SessionStore()
    started = handle_invoke(
        AllyInvokeRequest(op=InvokeOp.START, human=happy_path_input()),
        store,
    )
    assert started.handoff is not None
    locked = handle_invoke(
        AllyInvokeRequest(
            op=InvokeOp.APPLY_LOCK,
            session_id=started.session_id,
            lock=HumanStrategicLock(
                diagnosis_digest=started.handoff.diagnosis.digest(),
                signed_by="lead-b",
                signature="sig-lead-b",
                closed_decision_ids=[
                    point.id for point in started.handoff.diagnosis.open_decision_points
                ],
            ),
        ),
        store,
    )
    assert locked.error is None
    assert locked.interrupt is False
    assert locked.stage is Stage.HUMAN_STRATEGIC_LOCK
    assert locked.agent_handoff is None


def test_signed_lock_then_enter_execution_emits_typed_agent_handoff():
    store = SessionStore()
    started = handle_invoke(
        AllyInvokeRequest(op=InvokeOp.START, human=happy_path_input()),
        store,
    )
    assert started.handoff is not None
    handle_invoke(
        AllyInvokeRequest(
            op=InvokeOp.APPLY_LOCK,
            session_id=started.session_id,
            lock=HumanStrategicLock(
                diagnosis_digest=started.handoff.diagnosis.digest(),
                signed_by="lead-b",
                signature="sig-lead-b",
                closed_decision_ids=[
                    point.id for point in started.handoff.diagnosis.open_decision_points
                ],
            ),
        ),
        store,
    )
    released = handle_invoke(
        AllyInvokeRequest(
            op=InvokeOp.ENTER_EXECUTION,
            session_id=started.session_id,
            to_agent=ExecutionAgent.RCC,
        ),
        store,
    )
    assert released.error is None
    assert released.stage is Stage.EXECUTION
    assert released.agent_handoff is not None
    assert released.agent_handoff.to_agent is ExecutionAgent.RCC
    assert released.agent_handoff.lock.signature == "sig-lead-b"
    assert released.agent_handoff.from_agent == "ally"


def test_start_without_human_input_is_refused():
    response = handle_invoke(AllyInvokeRequest(op=InvokeOp.START), SessionStore())
    assert response.error_type == "RefusalError"
    assert response.handoff is None
    assert response.agent_handoff is None
