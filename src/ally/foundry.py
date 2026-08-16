"""Foundry Invocations adapter. Typed ops only — not a chat transcript."""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Never

from pydantic import BaseModel

from ally.contracts import (
    AgentHandoff,
    AllyStrategicDiagnosis,
    CritiqueReport,
    HumanHandoff,
    HumanInput,
    HumanStrategicLock,
    QuarantineRecord,
)
from ally.durable import DurableBackend, DurableWriteError, durable_from_env
from ally.enums import ExecutionAgent, Stage
from ally.exceptions import AllyError
from ally.memory import MemoryStore
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
    diagnosis_digest: str | None = None


class AllyInvokeResponse(BaseModel):
    """Blob-out contract. interrupt=true means Human Strategic Lock, not auto-execute."""

    session_id: str | None = None
    stage: Stage | None = None
    interrupt: bool = False
    handoff: HumanHandoff | None = None
    agent_handoff: AgentHandoff | None = None
    error_type: str | None = None
    error: str | None = None
    diagnosis_digest: str | None = None


class SessionSnapshot(BaseModel):
    """Durable Ally session. Survives the hosted-agent 15-minute idle deprovision."""

    session_id: str
    client_id: str
    brand_id: str
    lead_id: str
    diagnosis: AllyStrategicDiagnosis
    critique: CritiqueReport
    handoff: HumanHandoff
    quarantine: list[QuarantineRecord]
    stage: Stage
    lock: HumanStrategicLock | None = None

    @classmethod
    def from_session(cls, session: AllySession) -> SessionSnapshot:
        return cls(
            session_id=session.session_id,
            client_id=session.client_id,
            brand_id=session.brand_id,
            lead_id=session.lead_id,
            diagnosis=session.diagnosis,
            critique=session.critique,
            handoff=session.handoff,
            quarantine=list(session.quarantine),
            stage=session.stage,
            lock=session.lock,
        )

    def to_session(self) -> AllySession:
        session = AllySession(
            client_id=self.client_id,
            brand_id=self.brand_id,
            lead_id=self.lead_id,
            diagnosis=self.diagnosis,
            critique=self.critique,
            handoff=self.handoff,
            quarantine=list(self.quarantine),
            session_id=self.session_id,
        )
        session.stage = self.stage
        session.lock = self.lock
        return session


class SessionStore:
    """In-process map plus $HOME cache and external durable storage."""

    def __init__(
        self,
        persist_dir: Path | str | None = None,
        memory: MemoryStore | None = None,
        durable: DurableBackend | None = None,
    ) -> None:
        self._sessions: dict[str, AllySession] = {}
        self.memory = memory or MemoryStore()
        self._persist_dir = Path(persist_dir) if persist_dir is not None else None
        self._durable = durable
        if self._persist_dir is not None:
            self._persist_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def under_home(cls) -> SessionStore:
        home = Path(os.environ.get("HOME", "/tmp"))
        return cls(
            persist_dir=home / "ally-sessions",
            memory=MemoryStore.under_home(),
            durable=durable_from_env(),
        )

    def put(self, session: AllySession) -> AllySession:
        session.memory = self.memory
        self._sessions[session.session_id] = session
        self._write(session)
        self._write_durable(session)
        return session

    def get(self, session_id: str) -> AllySession | None:
        cached = self._sessions.get(session_id)
        if cached is not None:
            return cached
        loaded = self._read(session_id)
        if loaded is None:
            loaded = self._read_durable_session(session_id)
        if loaded is not None:
            self._sessions[session_id] = loaded
        return loaded

    def get_by_digest(self, digest: str) -> AllySession | None:
        for session in self._sessions.values():
            if session.diagnosis.digest() == digest:
                return session
        if self._persist_dir is not None:
            for path in self._persist_dir.glob("*.json"):
                try:
                    loaded = self._session_from_json(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if loaded is not None and loaded.diagnosis.digest() == digest:
                    self._sessions[loaded.session_id] = loaded
                    return loaded
        if self._durable is None:
            return None
        try:
            raw = self._durable.get_json_by_digest(digest)
        except Exception:
            return None
        if raw is None:
            return None
        loaded = self._session_from_json(raw)
        if loaded is not None:
            self._sessions[loaded.session_id] = loaded
        return loaded

    def _path(self, session_id: str) -> Path | None:
        if self._persist_dir is None:
            return None
        return self._persist_dir / f"{session_id}.json"

    def _write(self, session: AllySession) -> None:
        path = self._path(session.session_id)
        if path is None:
            return
        path.write_text(
            SessionSnapshot.from_session(session).model_dump_json(),
            encoding="utf-8",
        )

    def _read(self, session_id: str) -> AllySession | None:
        path = self._path(session_id)
        if path is None or not path.is_file():
            return None
        return self._session_from_json(path.read_text(encoding="utf-8"))

    def _write_durable(self, session: AllySession) -> None:
        if self._durable is None:
            return
        snapshot = SessionSnapshot.from_session(session)
        try:
            self._durable.put_json(
                session_id=session.session_id,
                digest=session.diagnosis.digest(),
                payload=snapshot.model_dump_json(),
            )
        except DurableWriteError:
            return

    def _read_durable_session(self, session_id: str) -> AllySession | None:
        if self._durable is None:
            return None
        try:
            raw = self._durable.get_json_by_session_id(session_id)
        except Exception:
            return None
        if raw is None:
            return None
        return self._session_from_json(raw)

    def _session_from_json(self, raw: str) -> AllySession | None:
        snapshot = SessionSnapshot.model_validate_json(raw)
        session = snapshot.to_session()
        session.memory = self.memory
        return session


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
    session = store.put(
        run_vertical_slice(
            request.human,
            retriever=retriever,
            memory=store.memory,
        )
    )
    return AllyInvokeResponse(
        session_id=session.session_id,
        stage=session.stage,
        interrupt=True,
        handoff=session.handoff,
        diagnosis_digest=session.diagnosis.digest(),
    )


def _apply_lock(request: AllyInvokeRequest, store: SessionStore) -> AllyInvokeResponse:
    session = _load_session(request.session_id, store, request.diagnosis_digest)
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
            diagnosis_digest=session.diagnosis.digest(),
        )
    try:
        session.apply_lock(request.lock)
    except AllyError as exc:
        return _error(session, exc, interrupt=True)
    store.put(session)
    return AllyInvokeResponse(
        session_id=session.session_id,
        stage=session.stage,
        interrupt=False,
        handoff=session.handoff,
        diagnosis_digest=session.diagnosis.digest(),
    )


def _enter_execution(
    request: AllyInvokeRequest, store: SessionStore
) -> AllyInvokeResponse:
    session = _load_session(request.session_id, store, request.diagnosis_digest)
    if isinstance(session, AllyInvokeResponse):
        return session
    try:
        handoff = session.enter_execution(to_agent=request.to_agent)
    except AllyError as exc:
        return _error(session, exc, interrupt=session.lock is None)
    store.put(session)
    return AllyInvokeResponse(
        session_id=session.session_id,
        stage=session.stage,
        interrupt=False,
        agent_handoff=handoff,
        diagnosis_digest=session.diagnosis.digest(),
    )


def _load_session(
    session_id: str | None,
    store: SessionStore,
    diagnosis_digest: str | None = None,
) -> AllySession | AllyInvokeResponse:
    if session_id:
        session = store.get(session_id)
        if session is not None:
            return session
    if diagnosis_digest:
        session = store.get_by_digest(diagnosis_digest)
        if session is not None:
            return session
    if not session_id and not diagnosis_digest:
        return AllyInvokeResponse(
            error_type="SequenceLockError",
            error="session_id or diagnosis_digest is required after start",
        )
    return AllyInvokeResponse(
        session_id=session_id,
        error_type="SequenceLockError",
        error=f"unknown session_id {session_id}",
        diagnosis_digest=diagnosis_digest,
    )


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
        diagnosis_digest=session.diagnosis.digest(),
    )


def _unhandled_op(op: Never) -> AllyInvokeResponse:
    raise AssertionError(f"unhandled invoke op: {op}")
