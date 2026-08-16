"""Foundry Invocations adapter. Typed ops only — not a chat transcript."""

from __future__ import annotations

from enum import Enum
from typing import Never

from pydantic import BaseModel

from ally.contracts import AgentHandoff, HumanHandoff, HumanInput, HumanStrategicLock
from ally.enums import ExecutionAgent, Stage
from ally.exceptions import AllyError
from ally.retrieval import StructuredRetriever
from ally.runtime import AllySession, run_vertical_slice


class InvokeOp(str, Enum):
    """Legal Foundry /invocations operations. Chat text is not an operation."""

    START = "start"
    APPLY_LOCK = "apply_lock"
    ENTER_EXECUTION = "enter_execution"


class AllyInvokeRequest(BaseModel):
    """Blob-in contract for POST /invocations. The platform does not interpret this."""

    op: InvokeOp
    session_id: str | None = None
    human: HumanInput | None = None
    lock: HumanStrategicLock | None = None
    to_agent: ExecutionAgent = ExecutionAgent.LEXIE


class AllyInvokeResponse(BaseModel):
    """Blob-out contract. interrupt=true means Human Strategic Lock, not auto-execute."""

    session_id: str | None = None
    stage: Stage | None = None
    interrupt: bool = False
    handoff: HumanHandoff | None = None
    agent_handoff: AgentHandoff | None = None
    error_type: str | None = None
    error: str | None = None


class SessionStore:
    """In-process session map. First deploy can persist under $HOME; Cosmos is later."""

    def __init__(self) -> None:
        self._sessions: dict[str, AllySession] = {}

    def put(self, session: AllySession) -> AllySession:
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> AllySession | None:
        return self._sessions.get(session_id)


def handle_invoke(
    request: AllyInvokeRequest,
    store: SessionStore,
    *,
    retriever: StructuredRetriever | None = None,
) -> AllyInvokeResponse:
    """Dispatch one Invocations payload onto the existing Ally state machine."""
    if request.op is InvokeOp.START:
        return _start(request, store, retriever=retriever)
    if request.op is InvokeOp.APPLY_LOCK:
        return _apply_lock(request, store)
    if request.op is InvokeOp.ENTER_EXECUTION:
        return _enter_execution(request, store)
    return _unhandled_op(request.op)


def _start(
    request: AllyInvokeRequest,
    store: SessionStore,
    *,
    retriever: StructuredRetriever | None,
) -> AllyInvokeResponse:
    if request.human is None:
        return AllyInvokeResponse(
            error_type="RefusalError",
            error="start requires a HumanInput object, not free text",
        )
    session = store.put(run_vertical_slice(request.human, retriever=retriever))
    return AllyInvokeResponse(
        session_id=session.session_id,
        stage=session.stage,
        interrupt=True,
        handoff=session.handoff,
    )


def _apply_lock(request: AllyInvokeRequest, store: SessionStore) -> AllyInvokeResponse:
    session = _load_session(request.session_id, store)
    if isinstance(session, AllyInvokeResponse):
        return session
    if request.lock is None:
        return AllyInvokeResponse(
            session_id=session.session_id,
            stage=session.stage,
            interrupt=True,
            handoff=session.handoff,
            error_type="LockGateError",
            error="apply_lock requires a HumanStrategicLock object",
        )
    try:
        session.apply_lock(request.lock)
    except AllyError as exc:
        return _error(session, exc, interrupt=True)
    return AllyInvokeResponse(
        session_id=session.session_id,
        stage=session.stage,
        interrupt=False,
        handoff=session.handoff,
    )


def _enter_execution(
    request: AllyInvokeRequest, store: SessionStore
) -> AllyInvokeResponse:
    session = _load_session(request.session_id, store)
    if isinstance(session, AllyInvokeResponse):
        return session
    try:
        handoff = session.enter_execution(to_agent=request.to_agent)
    except AllyError as exc:
        return _error(session, exc, interrupt=session.lock is None)
    return AllyInvokeResponse(
        session_id=session.session_id,
        stage=session.stage,
        interrupt=False,
        agent_handoff=handoff,
    )


def _load_session(
    session_id: str | None, store: SessionStore
) -> AllySession | AllyInvokeResponse:
    if not session_id:
        return AllyInvokeResponse(
            error_type="SequenceLockError",
            error="session_id is required after start",
        )
    session = store.get(session_id)
    if session is None:
        return AllyInvokeResponse(
            session_id=session_id,
            error_type="SequenceLockError",
            error=f"unknown session_id {session_id}",
        )
    return session


def _error(
    session: AllySession, exc: AllyError, *, interrupt: bool
) -> AllyInvokeResponse:
    return AllyInvokeResponse(
        session_id=session.session_id,
        stage=session.stage,
        interrupt=interrupt,
        handoff=session.handoff,
        error_type=type(exc).__name__,
        error=str(exc),
    )


def _unhandled_op(op: Never) -> AllyInvokeResponse:
    raise AssertionError(f"unhandled invoke op: {op}")
