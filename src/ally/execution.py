"""Lexie and RCC. They accept AgentHandoff only. Cheap models are an ablation."""

from __future__ import annotations

import os
from typing import Any, Never

from pydantic import BaseModel, ValidationError

from ally.contracts import AgentHandoff
from ally.enums import ExecutionAgent
from ally.exceptions import LockGateError, RefusalError
from ally.lock import verify_lock
from ally.writer import review_draft

ENV_ABLATION = "ALLY_EXECUTION_ABLATION"
ENV_EXECUTION_DEPLOYMENT = "AZURE_AI_EXECUTION_DEPLOYMENT"
DEFAULT_ABLATION_DEPLOYMENT = "gpt-4.1-mini"


class ExecutionAccept(BaseModel):
    accepted: bool
    to_agent: ExecutionAgent
    diagnosis_id: str
    unresolved: list[str]
    inferred: list[str]
    lock_signed_by: str
    craft_findings: list[str] = []
    ablation_model: str | None = None


def execution_ablation_enabled() -> bool:
    return os.environ.get(ENV_ABLATION, "").strip().lower() in {"1", "true", "yes"}


def execution_ablation_model() -> str | None:
    if not execution_ablation_enabled():
        return None
    return os.environ.get(ENV_EXECUTION_DEPLOYMENT, DEFAULT_ABLATION_DEPLOYMENT)


def accept_handoff(payload: AgentHandoff | dict[str, Any] | str) -> ExecutionAccept:
    handoff = _parse_handoff(payload)
    if handoff.lock is None:
        raise LockGateError("Lexie/RCC cannot receive a diagnosis lacking a lock signature")
    if not handoff.lock.signature.strip() or not handoff.lock.signed_by.strip():
        raise LockGateError("Lexie/RCC cannot receive a diagnosis lacking a lock signature")
    verify_lock(handoff.lock, handoff.lock.diagnosis_digest)
    findings = review_draft(" ".join(claim.text for claim in handoff.claims))
    return ExecutionAccept(
        accepted=True,
        to_agent=handoff.to_agent,
        diagnosis_id=handoff.diagnosis_id,
        unresolved=list(handoff.unresolved),
        inferred=list(handoff.inferred),
        lock_signed_by=handoff.lock.signed_by,
        craft_findings=[finding.message for finding in findings],
        ablation_model=execution_ablation_model(),
    )


def _parse_handoff(payload: AgentHandoff | dict[str, Any] | str) -> AgentHandoff:
    if isinstance(payload, AgentHandoff):
        return payload
    if isinstance(payload, str):
        try:
            return AgentHandoff.model_validate_json(payload)
        except ValidationError as exc:
            raise RefusalError(
                "Lexie/RCC accept only AgentHandoff JSON, not free text"
            ) from exc
    try:
        return AgentHandoff.model_validate(payload)
    except ValidationError as exc:
        raise RefusalError(
            "Lexie/RCC accept only AgentHandoff JSON, not free text"
        ) from exc


def _never(value: Never) -> Never:
    raise ValueError(f"unhandled execution agent: {value}")


def assert_agent(handoff: AgentHandoff, expected: ExecutionAgent) -> None:
    if handoff.to_agent is not expected:
        raise RefusalError(
            f"{expected.value} received a handoff addressed to {handoff.to_agent.value}"
        )
    if expected is ExecutionAgent.LEXIE or expected is ExecutionAgent.RCC:
        return
    _never(expected)
