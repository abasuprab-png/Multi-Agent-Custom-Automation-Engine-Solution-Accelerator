"""Sequence-locked Ally runtime. Stages are code, not a manager prompt."""

from __future__ import annotations

from uuid import uuid4

from ally.contracts import (
    AgentHandoff,
    AllyStrategicDiagnosis,
    CritiqueReport,
    HumanHandoff,
    HumanInput,
    HumanStrategicLock,
    OpenDecisionPoint,
    QuarantineRecord,
)
from ally.critique import run_self_critique
from ally.enums import (
    AllyPass,
    CritiqueCode,
    EpistemicStatus,
    ExecutionAgent,
    QuarantineReason,
    STAGE_ORDER,
    Stage,
)
from ally.exceptions import LockGateError, SequenceLockError
from ally.ingest import ingest_envelopes, inferred_texts, unresolved_texts
from ally.knowledge import query_canon
from ally.memory import MemoryStore
from ally.passes import pass_record


def next_stage(current: Stage) -> Stage | None:
    index = STAGE_ORDER.index(current)
    if index + 1 >= len(STAGE_ORDER):
        return None
    return STAGE_ORDER[index + 1]


def assert_transition(current: Stage, target: Stage) -> None:
    allowed = next_stage(current)
    if allowed is None or target is not allowed:
        raise SequenceLockError(
            f"Cannot enter {target.value} from {current.value}. "
            f"Required next stage is {allowed.value if allowed else 'none'}."
        )


class AllySession:
    """Post-slice workflow. Diagnosis, critique, and handoff are always present."""

    def __init__(
        self,
        *,
        client_id: str,
        brand_id: str,
        lead_id: str,
        diagnosis: AllyStrategicDiagnosis,
        critique: CritiqueReport,
        handoff: HumanHandoff,
        quarantine: list[QuarantineRecord],
        memory: MemoryStore | None = None,
        session_id: str | None = None,
    ) -> None:
        self.session_id = session_id or f"sess-{uuid4().hex[:12]}"
        self.client_id = client_id
        self.brand_id = brand_id
        self.lead_id = lead_id
        self.memory = memory or MemoryStore()
        self.diagnosis = diagnosis
        self.critique = critique
        self.handoff = handoff
        self.quarantine = quarantine
        self.stage = Stage.HUMAN_STRATEGIC_LOCK
        self.lock: HumanStrategicLock | None = None

    def apply_lock(self, lock: HumanStrategicLock) -> None:
        if self.stage is not Stage.HUMAN_STRATEGIC_LOCK:
            raise SequenceLockError(
                f"Lock requires stage {Stage.HUMAN_STRATEGIC_LOCK.value}, "
                f"current is {self.stage.value}"
            )
        if lock.diagnosis_digest != self.diagnosis.digest():
            raise LockGateError(
                "Lock diagnosis_digest does not match the session diagnosis"
            )
        leftover = {
            point.id for point in self.diagnosis.open_decision_points
        } - set(lock.closed_decision_ids)
        if leftover:
            raise LockGateError(
                "Lock does not close every blocking decision point: "
                + ", ".join(sorted(leftover))
            )
        self.lock = lock

    def enter_execution(
        self, *, to_agent: ExecutionAgent | str = ExecutionAgent.LEXIE
    ) -> AgentHandoff:
        lock = self._require_lock()
        assert_transition(self.stage, Stage.EXECUTION)
        self.stage = Stage.EXECUTION
        agent = (
            to_agent
            if isinstance(to_agent, ExecutionAgent)
            else ExecutionAgent(to_agent)
        )
        return AgentHandoff(
            to_agent=agent,
            diagnosis_id=self.diagnosis.id,
            claims=list(self.diagnosis.claims),
            unresolved=unresolved_texts(self.diagnosis.claims)
            + [item.label for item in self.diagnosis.unresolved_verification()],
            inferred=inferred_texts(self.diagnosis.claims),
            lock=lock,
        )

    def _require_lock(self) -> HumanStrategicLock:
        if self.lock is None:
            raise LockGateError(
                "Lexie/RCC cannot receive a diagnosis lacking a lock signature"
            )
        if self.lock.diagnosis_digest != self.diagnosis.digest():
            raise LockGateError("Lock signature does not match the current diagnosis")
        return self.lock


def run_vertical_slice(
    human: HumanInput, *, memory: MemoryStore | None = None
) -> AllySession:
    """Discovery → Counsel → Retrieval → Reconciliation → Human Lock interrupt."""
    claims, quarantine = ingest_envelopes(human.envelopes)
    diagnosis = AllyStrategicDiagnosis(
        client_id=human.client_id,
        brand_id=human.brand_id,
        lead_id=human.lead_id,
        task=human.task,
        claims=claims,
        spine_candidates=[human.spine] if human.spine is not None else [],
        open_verification=list(human.open_verification),
        canon_citations=[rule.id for rule in query_canon("ADM-1", "ADM-2")],
        pass_history=[
            pass_record(AllyPass.DISCOVERY_COUNSEL),
            pass_record(AllyPass.EVIDENCE_RECONCILIATION),
        ],
    )
    critique = run_self_critique(diagnosis)
    diagnosis, held = _hold_inferred_contradictions(diagnosis, critique)
    quarantine = [*quarantine, *held]
    diagnosis = diagnosis.model_copy(
        update={"open_decision_points": _decisions(diagnosis, critique)}
    )
    points = diagnosis.open_decision_points
    handoff = HumanHandoff(
        diagnosis=diagnosis,
        critique=critique,
        quarantine=list(quarantine),
        open_decision_points=points,
        summary=_handoff_summary(points),
    )
    return AllySession(
        client_id=human.client_id,
        brand_id=human.brand_id,
        lead_id=human.lead_id,
        diagnosis=diagnosis,
        critique=critique,
        handoff=handoff,
        quarantine=quarantine,
        memory=memory,
    )


def _hold_inferred_contradictions(
    diagnosis: AllyStrategicDiagnosis, report: CritiqueReport
) -> tuple[AllyStrategicDiagnosis, list[QuarantineRecord]]:
    detail_by_id = {
        claim_id: issue.message
        for issue in report.issues
        if issue.code is CritiqueCode.CROSS_CLAIM
        for claim_id in issue.claim_ids
    }
    inferred_ids = {
        claim_id
        for claim_id in detail_by_id
        if (claim := diagnosis.claim_by_id(claim_id)) is not None
        and claim.epistemic is EpistemicStatus.INFERRED
    }
    if not inferred_ids:
        return diagnosis, []
    kept = []
    held: list[QuarantineRecord] = []
    for claim in diagnosis.claims:
        if claim.id in inferred_ids:
            held.append(
                QuarantineRecord(
                    reason=QuarantineReason.CROSS_CLAIM,
                    source=claim.source,
                    origin_agent=claim.origin_agent,
                    text=claim.text,
                    detail=detail_by_id[claim.id],
                )
            )
        else:
            kept.append(claim)
    return diagnosis.model_copy(update={"claims": kept}), held


def _decisions(
    diagnosis: AllyStrategicDiagnosis, report: CritiqueReport
) -> list[OpenDecisionPoint]:
    points = [
        OpenDecisionPoint(
            prompt=issue.message,
            related_claim_ids=list(issue.claim_ids),
            related_codes=[issue.code],
        )
        for issue in report.issues
    ]
    points.extend(
        OpenDecisionPoint(
            prompt=f"Unresolved verification still open: {item.label}. {item.detail}",
            related_codes=[CritiqueCode.UNRESOLVED_OPEN],
        )
        for item in diagnosis.unresolved_verification()
    )
    return points


def _handoff_summary(points: list[OpenDecisionPoint]) -> str:
    if not points:
        return (
            "Human Strategic Lock interrupt. Diagnosis is internally consistent. "
            "Sign the lock to release Lexie/RCC, or override and record a correction."
        )
    return (
        "Human Strategic Lock interrupt. "
        f"{len(points)} thing(s) only you can close out: "
        + "; ".join(point.prompt for point in points[:2])
    )
