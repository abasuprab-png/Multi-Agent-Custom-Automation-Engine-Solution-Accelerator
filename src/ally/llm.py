"""Live Foundry Responses calls. Deterministic gates still run after this."""

from __future__ import annotations

import json
import logging
import os
from typing import Never, Protocol

from pydantic import BaseModel, Field

try:
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential
except ImportError:  # optional until the hosted image / [foundry] extra is installed
    AIProjectClient = None
    DefaultAzureCredential = None

from ally.contracts import AllyMessageSpineCandidate, Claim, HumanInput, PassRecord
from ally.enums import AllyPass
from ally.foundry_project import MODEL_DOING_DEPLOYMENT, MODEL_THINKING_DEPLOYMENT, PROJECT_ENDPOINT
from ally.passes import PASS_CONFIGS, pass_record
from ally.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

ENV_PROJECT_ENDPOINT = "FOUNDRY_PROJECT_ENDPOINT"
ENV_PROJECT_ENDPOINT_ALT = "AZURE_AI_PROJECT_ENDPOINT"
ENV_THINKING = "AZURE_AI_THINKING_DEPLOYMENT"
ENV_DOING = "AZURE_AI_DOING_DEPLOYMENT"
ENV_LIVE = "ALLY_LIVE_LLM"

NOTES_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "notes": {"type": "string"},
        "flagged_contradictions": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["notes", "flagged_contradictions", "open_questions"],
}


class AllyPassNotes(BaseModel):
    """Advisory model output. Never replaces ingest, critique, or the lock."""

    notes: str
    flagged_contradictions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class AllyLLM(Protocol):
    def run_pass(
        self,
        ally_pass: AllyPass,
        *,
        human: HumanInput,
        claims: list[Claim],
        spines: list[AllyMessageSpineCandidate],
        prior_notes: str | None = None,
    ) -> tuple[PassRecord, AllyPassNotes | None]: ...


class NoOpAllyLLM:
    """Pytest / local default. Records pass metadata and does not call a model."""

    def run_pass(
        self,
        ally_pass: AllyPass,
        *,
        human: HumanInput,
        claims: list[Claim],
        spines: list[AllyMessageSpineCandidate],
        prior_notes: str | None = None,
    ) -> tuple[PassRecord, AllyPassNotes | None]:
        del human, claims, spines, prior_notes
        return pass_record(ally_pass), None


def project_endpoint_from_env() -> str | None:
    return os.environ.get(ENV_PROJECT_ENDPOINT) or os.environ.get(ENV_PROJECT_ENDPOINT_ALT)


def thinking_deployment() -> str:
    return os.environ.get(ENV_THINKING) or MODEL_THINKING_DEPLOYMENT


def doing_deployment() -> str:
    return os.environ.get(ENV_DOING) or MODEL_DOING_DEPLOYMENT


def llm_enabled() -> bool:
    flag = os.environ.get(ENV_LIVE, "").strip().lower()
    return flag in {"1", "true", "yes"} and bool(project_endpoint_from_env())


def llm_from_env() -> AllyLLM:
    if not llm_enabled():
        return NoOpAllyLLM()
    return FoundryAllyLLM(
        endpoint=project_endpoint_from_env() or PROJECT_ENDPOINT,
        thinking_deployment=thinking_deployment(),
        doing_deployment=doing_deployment(),
    )


def _never(value: Never) -> Never:
    raise ValueError(f"unhandled Ally pass: {value}")


def _reasoning_effort(ally_pass: AllyPass) -> str:
    if ally_pass is AllyPass.DISCOVERY_COUNSEL:
        return "high"
    if ally_pass is AllyPass.EVIDENCE_RECONCILIATION:
        return "low"
    return _never(ally_pass)


def _pass_instructions(ally_pass: AllyPass) -> str:
    if ally_pass is AllyPass.DISCOVERY_COUNSEL:
        return (
            "This is Discovery+Counsel (thinking, gpt-5.6-sol). "
            "Read the ingested claims and spine. Name contradictions, missing "
            "admissibility answers, and genre defects. Do not invent facts. "
            "Do not rewrite verified claims. Do not release Lexie/RCC."
        )
    if ally_pass is AllyPass.EVIDENCE_RECONCILIATION:
        return (
            "This is Evidence Reconciliation (doing, gpt-5.6-terra). "
            "Re-read at low temperature. Flag GI-AE vs discontinuation spin, "
            "estimand-less percentages, and intensifiers without a cited number. "
            "Do not drop verified claims. Do not auto-execute."
        )
    return _never(ally_pass)


def _deployment_for(ally_pass: AllyPass, thinking: str, doing: str) -> str:
    if ally_pass is AllyPass.DISCOVERY_COUNSEL:
        return thinking
    if ally_pass is AllyPass.EVIDENCE_RECONCILIATION:
        return doing
    return _never(ally_pass)


class FoundryAllyLLM:
    """AIProjectClient → Responses API. Same project, two Direct-from-Azure deployments."""

    def __init__(
        self,
        *,
        endpoint: str,
        thinking_deployment: str,
        doing_deployment: str,
    ) -> None:
        self.endpoint = endpoint
        self.thinking_deployment = thinking_deployment
        self.doing_deployment = doing_deployment
        self._client = None

    def run_pass(
        self,
        ally_pass: AllyPass,
        *,
        human: HumanInput,
        claims: list[Claim],
        spines: list[AllyMessageSpineCandidate],
        prior_notes: str | None = None,
    ) -> tuple[PassRecord, AllyPassNotes | None]:
        deployment = _deployment_for(
            ally_pass, self.thinking_deployment, self.doing_deployment
        )
        try:
            notes = self._call(ally_pass, human, claims, spines, prior_notes, deployment)
        except Exception as exc:
            logger.warning("Foundry pass %s failed: %s", ally_pass.value, exc)
            return pass_record(ally_pass, live=False, error=str(exc)), None
        return pass_record(ally_pass, live=True), notes

    def _openai(self):
        if AIProjectClient is None or DefaultAzureCredential is None:
            raise RuntimeError("azure-ai-projects and azure-identity are required for live passes")
        if self._client is None:
            project = AIProjectClient(self.endpoint, DefaultAzureCredential())
            self._client = project.get_openai_client()
        return self._client

    def _call(
        self,
        ally_pass: AllyPass,
        human: HumanInput,
        claims: list[Claim],
        spines: list[AllyMessageSpineCandidate],
        prior_notes: str | None,
        deployment: str,
    ) -> AllyPassNotes:
        config = PASS_CONFIGS[ally_pass]
        payload = {
            "client_id": human.client_id,
            "brand_id": human.brand_id,
            "lead_id": human.lead_id,
            "task": human.task,
            "claims": [claim.model_dump(mode="json") for claim in claims],
            "spines": [spine.model_dump(mode="json") for spine in spines],
            "prior_notes": prior_notes,
        }
        request = {
            "model": deployment,
            "instructions": f"{SYSTEM_PROMPT}\n\n{_pass_instructions(ally_pass)}",
            "input": json.dumps(payload),
            "temperature": config.temperature,
            "reasoning": {"effort": _reasoning_effort(ally_pass)},
            "max_output_tokens": 800,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "ally_pass_notes",
                    "strict": True,
                    "schema": NOTES_SCHEMA,
                }
            },
        }
        try:
            response = self._openai().responses.create(**request)
        except Exception:
            request.pop("temperature", None)
            response = self._openai().responses.create(**request)
        text = getattr(response, "output_text", None) or ""
        if not text:
            raise ValueError("Responses API returned empty output_text")
        return AllyPassNotes.model_validate_json(text)
