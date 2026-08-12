"""Sequence-locked Ally runtime. Stages are code, not a manager prompt."""

from __future__ import annotations

import hashlib
import json
from typing import Never, NoReturn
from uuid import uuid4

from ally.contracts import (
    AgentHandoff,
    AllyStrategicDiagnosis,
    Claim,
    CritiqueReport,
    HumanHandoff,
    HumanInput,
    HumanStrategicLock,
    OpenDecisionPoint,
    PassRecord,
    QuarantineRecord,
    SliceResult,
)
from ally.critique import run_self_critique
from ally.enums import (
    AllyPass,
    CorrectionCategory,
    CritiqueCode,
    EpistemicStatus,
    LockState,
    QuarantineReason,
    Stage,
)
from ally.exceptions import LockGateError, RefusalError, SequenceLockError
from ally.ingest import ingest_envelope, inferred_texts, unresolved_texts
from ally.knowledge import query_canon
from ally.memory import MemoryStore
from ally.passes import PASS_CONFIGS, temperature_for


def assert_never(value: Never) -> NoReturn:
    raise AssertionError(f"Unhandled variant: {value!r}")


def next_stage(current: Stage) -> Stage | None:
    match current:
        case Stage.DISCOVERY:
            return Stage.COUNSEL
        case Stage.COUNSEL:
            return Stage.STRUCTURED_RETRIEVAL
        case Stage.STRUCTURED_RETRIEVAL:
            return Stage.EVIDENCE_RECONCILIATION
        case Stage.EVIDENCE_RECONCILIATION:
            return Stage.HUMAN_STRATEGIC_LOCK
        case Stage.HUMAN_STRATEGIC_LOCK:
            return Stage.EXECUTION
        case Stage.EXECUTION:
            return None
        case _:
            assert_never(current)


def diagnosis_digest(diagnosis: AllyStrategicDiagnosis) -> str:
    payload = diagnosis.model_dump(mode="json", exclude={"created_at", "pass_history"})
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AllySession:
    def __init__(
        self,
        *,
        client_id: str,
        brand_id: str,
        lead_id: str,
        memory: MemoryStore | None = None,
        session_id: str | None = None,
    ) -> None:
        self.session_id = session_id or f"sess-{uuid4().hex[:12]}"
        self.client_id = client_id
        self.brand_id = brand_id
        self.lead_id = lead_id
        self.memory = memory or MemoryStore()
        self.stage = Stage.DISCOVERY
        self.lock_state = LockState.NOT_REACHED
        self.lock: HumanStrategicLock | None = None
        self.diagnosis: AllyStrategicDiagnosis | None = None
        self.quarantine: list[QuarantineRecord] = []
        self.critique: CritiqueReport | None = None

    def advance_to(self, target: Stage) -> None:
        if target is self.stage:
            return
        allowed = next_stage(self.stage)
        if allowed is None or target is not allowed:
            raise SequenceLockError(
                f"Cannot enter {target.value} from {self.stage.value}. "
                f"Required next stage is {allowed.value if allowed else 'none'}."
            )
        if target is Stage.EXECUTION:
            self._require_signed_lock()
        self.stage = target

    def _require_signed_lock(self) -> None:
        if self.lock is None or self.lock_state is not LockState.SIGNED:
            raise LockGateError(
                "Lexie/RCC cannot receive a diagnosis lacking a lock signature"
            )
        if self.diagnosis is None:
            raise LockGateError("No diagnosis bound to this session")
        digest = diagnosis_digest(self.diagnosis)
        if self.lock.diagnosis_digest != digest:
            raise LockGateError("Lock signature does not match the current diagnosis")

    def _require_stage(self, expected: Stage) -> None:
        if self.stage is not expected:
            raise SequenceLockError(
                f"Action requires stage {expected.value}, current is {self.stage.value}"
            )

    def _record_pass(self, ally_pass: AllyPass) -> PassRecord:
        config = PASS_CONFIGS[ally_pass]
        record = PassRecord(
            ally_pass=ally_pass,
            model_tier=config.model_tier,
            temperature=temperature_for(ally_pass),
            thinking_budget=config.thinking_budget,
        )
        if self.diagnosis is not None:
            self.diagnosis.pass_history.append(record)
        return record

    def hold(self, record: QuarantineRecord) -> None:
        self.quarantine.append(record)

    def run_discovery_counsel(self, human: HumanInput) -> AllyStrategicDiagnosis:
        self._require_stage(Stage.DISCOVERY)
        if human.client_id != self.client_id or human.brand_id != self.brand_id:
            raise RefusalError("Human input client/brand does not match the session partition")
        claims: list[Claim] = []
        for envelope in human.envelopes:
            result = ingest_envelope(envelope)
            if isinstance(result, QuarantineRecord):
                self.hold(result)
            else:
                claims.append(result)
        spines = [human.spine] if human.spine is not None else []
        self.diagnosis = AllyStrategicDiagnosis(
            client_id=human.client_id,
            brand_id=human.brand_id,
            lead_id=human.lead_id,
            task=human.task,
            claims=claims,
            spine_candidates=spines,
            open_verification=list(human.open_verification),
        )
        self._record_pass(AllyPass.DISCOVERY_COUNSEL)
        self.advance_to(Stage.COUNSEL)
        return self.diagnosis

    def run_structured_retrieval(self) -> AllyStrategicDiagnosis:
        self._require_stage(Stage.COUNSEL)
        if self.diagnosis is None:
            raise SequenceLockError("Counsel produced no diagnosis")
        rules = query_canon("ADM-1", "ADM-2")
        self.diagnosis.canon_citations = [rule.id for rule in rules]
        self.advance_to(Stage.STRUCTURED_RETRIEVAL)
        return self.diagnosis

    def run_reconciliation(self) -> CritiqueReport:
        self._require_stage(Stage.STRUCTURED_RETRIEVAL)
        if self.diagnosis is None:
            raise SequenceLockError("No diagnosis to reconcile")
        self._record_pass(AllyPass.EVIDENCE_RECONCILIATION)
        report = run_self_critique(self.diagnosis)
        self.critique = report
        self._quarantine_inferred_contradictions(report)
        self._open_decisions_from(report)
        self.advance_to(Stage.EVIDENCE_RECONCILIATION)
        return report

    def _quarantine_inferred_contradictions(self, report: CritiqueReport) -> None:
        assert self.diagnosis is not None
        for issue in report.issues:
            if issue.code is not CritiqueCode.CROSS_CLAIM:
                continue
            inferred_ids = [
                claim_id
                for claim_id in issue.claim_ids
                if (claim := self.diagnosis.claim_by_id(claim_id)) is not None
                and claim.epistemic is EpistemicStatus.INFERRED
            ]
            kept: list[Claim] = []
            for claim in self.diagnosis.claims:
                if claim.id in inferred_ids:
                    self.hold(
                        QuarantineRecord(
                            reason=QuarantineReason.CROSS_CLAIM,
                            source=claim.source,
                            origin_agent=claim.origin_agent,
                            text=claim.text,
                            detail=issue.message,
                        )
                    )
                else:
                    kept.append(claim)
            self.diagnosis.claims = kept

    def _open_decisions_from(self, report: CritiqueReport) -> None:
        assert self.diagnosis is not None
        for issue in report.blocking:
            self.diagnosis.open_decision_points.append(
                OpenDecisionPoint(
                    prompt=issue.message,
                    blocking=True,
                    related_claim_ids=list(issue.claim_ids),
                    related_codes=[issue.code],
                )
            )
        for item in self.diagnosis.unresolved_verification():
            self.diagnosis.open_decision_points.append(
                OpenDecisionPoint(
                    prompt=f"Unresolved verification still open: {item.label}. {item.detail}",
                    blocking=True,
                    related_codes=[CritiqueCode.UNRESOLVED_OPEN],
                )
            )

    def request_human_lock(self) -> HumanHandoff:
        self._require_stage(Stage.EVIDENCE_RECONCILIATION)
        if self.diagnosis is None or self.critique is None:
            raise SequenceLockError("Reconciliation has not produced a critique")
        points = list(self.diagnosis.open_decision_points)
        blocking = [point for point in points if point.blocking]
        if blocking:
            summary = (
                "Human Strategic Lock interrupt. "
                f"{len(blocking)} thing(s) only you can close out: "
                + "; ".join(point.prompt for point in blocking[:2])
            )
        else:
            summary = (
                "Human Strategic Lock interrupt. Diagnosis is internally consistent. "
                "Sign the lock to release Lexie/RCC, or override and record a correction."
            )
        handoff = HumanHandoff(
            diagnosis=self.diagnosis,
            critique=self.critique,
            quarantine=list(self.quarantine),
            open_decision_points=points,
            summary=summary,
        )
        self.advance_to(Stage.HUMAN_STRATEGIC_LOCK)
        self.lock_state = LockState.AWAITING_SIGNATURE
        return handoff

    def apply_lock(self, lock: HumanStrategicLock) -> None:
        self._require_stage(Stage.HUMAN_STRATEGIC_LOCK)
        if self.diagnosis is None:
            raise LockGateError("No diagnosis to lock")
        digest = diagnosis_digest(self.diagnosis)
        if lock.diagnosis_digest != digest:
            raise LockGateError("Lock diagnosis_digest does not match the session diagnosis")
        blocking_ids = {
            point.id
            for point in self.diagnosis.open_decision_points
            if point.blocking
        }
        closed = set(lock.closed_decision_ids) | set(lock.accepted_unresolved_ids)
        leftover = blocking_ids - closed
        if leftover:
            raise LockGateError(
                "Lock does not close every blocking decision point: "
                + ", ".join(sorted(leftover))
            )
        self.lock = lock
        self.lock_state = LockState.SIGNED

    def record_override(self, category: CorrectionCategory, note: str) -> None:
        self.memory.record_correction(self.client_id, category, note)

    def enter_execution(self, *, to_agent: str = "lexie") -> AgentHandoff:
        self.advance_to(Stage.EXECUTION)
        assert self.diagnosis is not None
        assert self.lock is not None
        return AgentHandoff(
            from_agent="ally",
            to_agent=to_agent,
            diagnosis_id=self.diagnosis.id,
            claims=list(self.diagnosis.claims),
            unresolved=unresolved_texts(self.diagnosis.claims)
            + [item.label for item in self.diagnosis.unresolved_verification()],
            inferred=inferred_texts(self.diagnosis.claims),
            lock=self.lock,
        )


def run_vertical_slice(
    human: HumanInput, *, memory: MemoryStore | None = None
) -> tuple[AllySession, SliceResult]:
    """Discovery → Counsel → Retrieval → Reconciliation → Human Lock interrupt."""
    try:
        session = AllySession(
            client_id=human.client_id,
            brand_id=human.brand_id,
            lead_id=human.lead_id,
            memory=memory,
        )
        session.run_discovery_counsel(human)
        session.run_structured_retrieval()
        session.run_reconciliation()
        handoff = session.request_human_lock()
    except RefusalError as exc:
        empty = AllySession(
            client_id=human.client_id or "unknown",
            brand_id=human.brand_id or "unknown",
            lead_id=human.lead_id or "unknown",
            memory=memory,
        )
        return empty, SliceResult(
            status="refused",
            session_id=empty.session_id,
            stage=Stage.DISCOVERY,
            refusal=str(exc),
        )
    blocking_quarantine = [
        record
        for record in session.quarantine
        if record.reason
        in {QuarantineReason.MISSING_EPISTEMIC, QuarantineReason.IDENTITY_INFERENCE}
    ]
    if blocking_quarantine and not (session.diagnosis and session.diagnosis.claims):
        result_status = "quarantined"
    else:
        result_status = "awaiting_human_lock"
    result = SliceResult(
        status=result_status,
        session_id=session.session_id,
        stage=session.stage,
        diagnosis=session.diagnosis,
        critique=session.critique,
        handoff=handoff,
        quarantine=list(session.quarantine),
    )
    return session, result
