"""Lexie/RCC accept only AgentHandoff. Lock overrides record correction categories."""

import pytest

from ally.contracts import HumanStrategicLock
from ally.enums import CorrectionCategory, ExecutionAgent
from ally.exceptions import RefusalError
from ally.execution import accept_handoff
from ally.fixtures import gi_ae_contradiction_input, happy_path_input
from ally.foundry import AllyInvokeRequest, InvokeOp, SessionStore, handle_invoke
from ally.memory import MemoryStore


def test_lexie_rejects_free_text():
    with pytest.raises(RefusalError, match="AgentHandoff"):
        accept_handoff("please draft the press release")


def test_signed_handoff_is_accepted_by_lexie():
    store = SessionStore(memory=MemoryStore())
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
            to_agent=ExecutionAgent.LEXIE,
        ),
        store,
    )
    assert released.agent_handoff is not None
    accepted = accept_handoff(released.agent_handoff)
    assert accepted.accepted is True
    assert accepted.to_agent is ExecutionAgent.LEXIE
    assert accepted.lock_signed_by == "lead-b"
    assert accepted.ablation_model is None


def test_lock_override_records_partitioned_corrections(tmp_path):
    memory = MemoryStore(persist_dir=tmp_path)
    store = SessionStore(memory=memory)
    started = handle_invoke(
        AllyInvokeRequest(op=InvokeOp.START, human=gi_ae_contradiction_input()),
        store,
    )
    assert started.handoff is not None
    handle_invoke(
        AllyInvokeRequest(
            op=InvokeOp.APPLY_LOCK,
            session_id=started.session_id,
            lock=HumanStrategicLock(
                diagnosis_digest=started.handoff.diagnosis.digest(),
                signed_by="lead-a",
                signature="sig-override",
                closed_decision_ids=[
                    point.id for point in started.handoff.open_decision_points
                ],
            ),
        ),
        store,
    )
    counts = memory.category_counts("novartis-pilot")
    assert counts.get(CorrectionCategory.CROSS_CLAIM, 0) >= 1
    assert counts.get(CorrectionCategory.GENRE, 0) >= 1
    assert memory.corrections_for("other-brand") == []
    reloaded = MemoryStore(persist_dir=tmp_path)
    assert reloaded.category_counts("novartis-pilot")[CorrectionCategory.CROSS_CLAIM] >= 1
