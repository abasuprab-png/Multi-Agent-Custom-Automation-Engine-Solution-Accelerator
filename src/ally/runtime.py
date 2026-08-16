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
    StrategicInsight,
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
from ally.lock import verify_lock
from ally.insight import insight_from_notes
from ally.ingest import ingest_envelopes, inferred_texts, unresolved_texts
from ally.cams import CamsReader
from ally.clinical import retriever_from_env
from ally.knowledge import query_canon
from ally.llm import AllyLLM, llm_from_env
from ally.memory import MemoryStore, category_for_code
from ally.retrieval import RetrievalQuery, StructuredRetriever, prefer_primary
from ally.web import WebSearcher, searcher_from_env


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
        verify_lock(lock, self.diagnosis.digest())
        leftover = {
            point.id for point in self.diagnosis.open_decision_points
        } - set(lock.closed_decision_ids)
        if leftover:
            raise LockGateError(
                "Lock does not close every blocking decision point: "
                + ", ".join(sorted(leftover))
            )
        self.lock = lock
        self._record_lock_overrides(lock)

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
            insight=self.diagnosis.insight,
            lock=lock,
        )

    def _require_lock(self) -> HumanStrategicLock:
        if self.lock is None:
            raise LockGateError(
                "Lexie/RCC cannot receive a diagnosis lacking a lock signature"
            )
        verify_lock(self.lock, self.diagnosis.digest())
        return self.lock

    def _record_lock_overrides(self, lock: HumanStrategicLock) -> None:
        closed = set(lock.closed_decision_ids)
        for point in self.diagnosis.open_decision_points:
            if point.id not in closed:
                continue
            for code in point.related_codes:
                self.memory.record_correction(
                    self.client_id,
                    category_for_code(code),
                    point.prompt,
                )
        self.memory.remember_lead(self.client_id, lock.signed_by, "signed lock")


def run_vertical_slice(
    human: HumanInput,
    *,
    memory: MemoryStore | None = None,
    retriever: StructuredRetriever | None = None,
    llm: AllyLLM | None = None,
    searcher: WebSearcher | None = None,
    cams: CamsReader | None = None,
) -> AllySession:
    """Discovery → Counsel → Retrieval → Reconciliation → Human Lock interrupt."""
    runner = llm if llm is not None else llm_from_env()
    claims, quarantine = ingest_envelopes(human.envelopes)
    web = searcher if searcher is not None else searcher_from_env()
    if web is not None:
        web_claims, web_held = ingest_envelopes(web.search(human))
        claims = [*claims, *web_claims]
        quarantine = [*quarantine, *web_held]
    if cams is not None:
        cams_claims, cams_held = ingest_envelopes(cams.read(human.client_id, human.brand_id))
        claims = [*claims, *cams_claims]
        quarantine = [*quarantine, *cams_held]
    source = retriever if retriever is not None else retriever_from_env()
    if source is not None:
        primary, held_primary = ingest_envelopes(
            source.fetch(
                RetrievalQuery(
                    brand_id=human.brand_id,
                    task=human.task,
                    nct_id=human.nct_id,
                )
            )
        )
        claims, superseded = prefer_primary(claims, primary)
        quarantine = [*quarantine, *held_primary, *superseded]
        claims = [*claims, *primary]
    spines = [human.spine] if human.spine is not None else []
    counsel_record, counsel = runner.run_pass(
        AllyPass.DISCOVERY_COUNSEL,
        human=human,
        claims=claims,
        spines=spines,
    )
    recon_record, recon = runner.run_pass(
        AllyPass.EVIDENCE_RECONCILIATION,
        human=human,
        claims=claims,
        spines=spines,
        prior_notes=counsel.notes if counsel is not None else None,
    )
    diagnosis = AllyStrategicDiagnosis(
        client_id=human.client_id,
        brand_id=human.brand_id,
        lead_id=human.lead_id,
        task=human.task,
        claims=claims,
        spine_candidates=spines,
        insight=_assemble_insight(human, counsel),
        open_verification=list(human.open_verification),
        canon_citations=[
            rule.id
            for rule in query_canon(
                "ADM-1", "ADM-2", "SI-1", "SI-2", "SI-3", "SI-4", "SI-5"
            )
        ],
        pass_history=[counsel_record, recon_record],
        counsel_notes=counsel.notes if counsel is not None else None,
        reconciliation_notes=recon.notes if recon is not None else None,
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
                QuarantineRecord.hold_claim(
                    claim,
                    QuarantineReason.CROSS_CLAIM,
                    detail_by_id[claim.id],
                )
            )
        else:
            kept.append(claim)
    return diagnosis.model_copy(update={"claims": kept}), held


def _assemble_insight(human: HumanInput, counsel: object | None) -> StrategicInsight | None:
    if human.insight is not None:
        return human.insight
    if counsel is None:
        return None
    return insight_from_notes(counsel)


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
