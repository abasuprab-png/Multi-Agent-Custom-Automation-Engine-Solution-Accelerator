"""Typed objects for every Ally handoff. Free text is not a legal inter-agent payload."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from ally.enums import (
    AllyPass,
    ChecklistAnswer,
    ClaimSource,
    CritiqueCode,
    EpistemicStatus,
    EstimandBasis,
    ExecutionAgent,
    Genre,
    QuarantineReason,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


class PassConfig(BaseModel):
    """Inference parameters for one Ally internal pass. Reconciliation is not cheaper."""

    ally_pass: AllyPass
    model_tier: Literal["frontier_reasoning"] = "frontier_reasoning"
    temperature: float
    thinking_budget: Literal["generous", "tight"]


class PassRecord(BaseModel):
    ally_pass: AllyPass
    model_tier: str
    temperature: float
    thinking_budget: str
    ran_at: datetime = Field(default_factory=_utcnow)


class Claim(BaseModel):
    """One atomic assertion. Source never implies truth; epistemic must be explicit."""

    id: str = Field(default_factory=lambda: _new_id("claim"))
    text: str
    source: ClaimSource
    epistemic: EpistemicStatus
    origin_agent: str | None = None
    citation: str | None = None
    estimand: EstimandBasis | None = None
    numeric_anchors: list[str] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def _nonempty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("claim text cannot be empty")
        return stripped


class InboundEnvelope(BaseModel):
    """Raw inbound payload. Missing epistemic is a quarantine event, not a default."""

    source: ClaimSource
    text: str
    origin_agent: str | None = None
    citation: str | None = None
    epistemic: EpistemicStatus | None = None
    estimand: EstimandBasis | None = None
    numeric_anchors: list[str] = Field(default_factory=list)
    supports_fact_id: str | None = None


class QuarantineRecord(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("q"))
    reason: QuarantineReason
    source: ClaimSource
    origin_agent: str | None = None
    text: str
    detail: str
    held_at: datetime = Field(default_factory=_utcnow)

    @classmethod
    def hold(
        cls,
        envelope: InboundEnvelope,
        reason: QuarantineReason,
        detail: str,
    ) -> QuarantineRecord:
        return cls(
            reason=reason,
            source=envelope.source,
            origin_agent=envelope.origin_agent,
            text=envelope.text,
            detail=detail,
        )

    @classmethod
    def hold_claim(
        cls, claim: Claim, reason: QuarantineReason, detail: str
    ) -> QuarantineRecord:
        return cls(
            reason=reason,
            source=claim.source,
            origin_agent=claim.origin_agent,
            text=claim.text,
            detail=detail,
        )


class OpenVerificationItem(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("ov"))
    label: str
    detail: str
    resolved: bool = False


class OpenDecisionPoint(BaseModel):
    """A question only the Human Strategic Lead can close."""

    id: str = Field(default_factory=lambda: _new_id("od"))
    prompt: str
    related_claim_ids: list[str] = Field(default_factory=list)
    related_codes: list[CritiqueCode] = Field(default_factory=list)


class AllyMessageSpineCandidate(BaseModel):
    """Buyer-facing spine. Admissibility fields are answers, not optional flavor."""

    id: str = Field(default_factory=lambda: _new_id("spine"))
    genre: Genre
    lede: str
    catalyst_external: ChecklistAnswer = ChecklistAnswer.UNANSWERED
    catalyst_dated: ChecklistAnswer = ChecklistAnswer.UNANSWERED
    catalyst_date: str | None = None
    tension_market_held: ChecklistAnswer = ChecklistAnswer.UNANSWERED
    tension_observable_marker: str | None = None
    claim_ids: list[str] = Field(default_factory=list)

    def catalyst_admissible(self) -> bool:
        return (
            self.catalyst_external is ChecklistAnswer.YES
            and self.catalyst_dated is ChecklistAnswer.YES
            and bool(self.catalyst_date)
        )

    def tension_admissible(self) -> bool:
        return (
            self.tension_market_held is ChecklistAnswer.YES
            and bool((self.tension_observable_marker or "").strip())
        )


class CritiqueIssue(BaseModel):
    code: CritiqueCode
    rule_id: str
    message: str
    claim_ids: list[str] = Field(default_factory=list)
    spine_id: str | None = None


class CritiqueReport(BaseModel):
    issues: list[CritiqueIssue] = Field(default_factory=list)
    ran_at: datetime = Field(default_factory=_utcnow)

    @property
    def passed(self) -> bool:
        return not self.issues


class AllyStrategicDiagnosis(BaseModel):
    id: str = Field(default_factory=lambda: _new_id("dx"))
    client_id: str
    brand_id: str
    lead_id: str
    task: str
    claims: list[Claim] = Field(default_factory=list)
    spine_candidates: list[AllyMessageSpineCandidate] = Field(default_factory=list)
    open_verification: list[OpenVerificationItem] = Field(default_factory=list)
    open_decision_points: list[OpenDecisionPoint] = Field(default_factory=list)
    canon_citations: list[str] = Field(default_factory=list)
    pass_history: list[PassRecord] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)

    def claim_by_id(self, claim_id: str) -> Claim | None:
        for claim in self.claims:
            if claim.id == claim_id:
                return claim
        return None

    def unresolved_verification(self) -> list[OpenVerificationItem]:
        return [item for item in self.open_verification if not item.resolved]

    def digest(self) -> str:
        payload = self.model_dump(mode="json", exclude={"created_at", "pass_history"})
        canonical = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class HumanStrategicLock(BaseModel):
    """Object-model gate. Execution constructors must require this, not a prompt."""

    diagnosis_digest: str
    signed_by: str
    signature: str
    closed_decision_ids: list[str] = Field(default_factory=list)
    signed_at: datetime = Field(default_factory=_utcnow)

    @field_validator("signature", "signed_by", "diagnosis_digest")
    @classmethod
    def _required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("lock fields cannot be empty")
        return value.strip()


class HumanHandoff(BaseModel):
    diagnosis: AllyStrategicDiagnosis
    critique: CritiqueReport
    quarantine: list[QuarantineRecord] = Field(default_factory=list)
    open_decision_points: list[OpenDecisionPoint] = Field(default_factory=list)
    summary: str


class DelegationBrief(BaseModel):
    """Structured brief. Downstream agents may not infer identity or extra facts."""

    task: str
    stated_facts: list[Claim]
    allowed_identities: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    inferred: list[str] = Field(default_factory=list)


class AgentHandoff(BaseModel):
    """Lexie/RCC payload. A missing lock is a schema error, not a runtime warning."""

    from_agent: Literal["ally"] = "ally"
    to_agent: ExecutionAgent
    diagnosis_id: str
    claims: list[Claim]
    unresolved: list[str] = Field(default_factory=list)
    inferred: list[str] = Field(default_factory=list)
    lock: HumanStrategicLock


class HumanInput(BaseModel):
    client_id: str
    brand_id: str
    lead_id: str
    task: str
    envelopes: list[InboundEnvelope] = Field(default_factory=list)
    open_verification: list[OpenVerificationItem] = Field(default_factory=list)
    spine: AllyMessageSpineCandidate | None = None
    nct_id: str | None = None

    @field_validator("client_id", "brand_id", "lead_id", "task")
    @classmethod
    def _required_scope(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("client_id, brand_id, lead_id, and task are required")
        return value.strip()
