"""Live LLM is env-gated. Injected fakes must not replace deterministic gates."""

from ally.enums import AllyPass, CritiqueCode
from ally.fixtures import gi_ae_contradiction_input
from ally.foundry_project import MODEL_DOING_DEPLOYMENT, MODEL_THINKING_DEPLOYMENT
from ally.llm import (
    MAX_OUTPUT_TOKENS,
    NOTES_MAX_LENGTH,
    NOTES_SCHEMA,
    AllyPassNotes,
    NoOpAllyLLM,
    extract_json_object,
    llm_enabled,
    llm_from_env,
    notes_from_response,
    parse_pass_notes,
)
from ally.passes import DISCOVERY_COUNSEL, EVIDENCE_RECONCILIATION, pass_record
from ally.runtime import run_vertical_slice


class _FakeLLM:
    def __init__(self) -> None:
        self.calls: list[AllyPass] = []

    def run_pass(self, ally_pass, *, human, claims, spines, prior_notes=None):
        self.calls.append(ally_pass)
        notes = AllyPassNotes(
            notes=f"fake-{ally_pass.value}",
            flagged_contradictions=["gi-ae"],
            open_questions=["catalyst"],
        )
        return pass_record(ally_pass, live=True), notes


def test_pytest_default_is_noop_and_not_live(monkeypatch):
    monkeypatch.delenv("ALLY_LIVE_LLM", raising=False)
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_AI_PROJECT_ENDPOINT", raising=False)
    assert llm_enabled() is False
    assert isinstance(llm_from_env(), NoOpAllyLLM)
    session = run_vertical_slice(gi_ae_contradiction_input())
    assert all(not record.live for record in session.diagnosis.pass_history)
    assert session.diagnosis.counsel_notes is None
    assert session.diagnosis.reconciliation_notes is None


def test_thinking_is_sol_doing_is_terra():
    assert DISCOVERY_COUNSEL.work == "thinking"
    assert DISCOVERY_COUNSEL.deployment_name == MODEL_THINKING_DEPLOYMENT == "gpt-5.6-sol"
    assert EVIDENCE_RECONCILIATION.work == "doing"
    assert EVIDENCE_RECONCILIATION.deployment_name == MODEL_DOING_DEPLOYMENT == "gpt-5.6-terra"


def test_fake_llm_notes_do_not_bypass_gi_ae_or_lock():
    fake = _FakeLLM()
    session = run_vertical_slice(gi_ae_contradiction_input(), llm=fake)
    assert fake.calls == [AllyPass.DISCOVERY_COUNSEL, AllyPass.EVIDENCE_RECONCILIATION]
    assert session.diagnosis.counsel_notes == "fake-discovery_counsel"
    assert session.diagnosis.reconciliation_notes == "fake-evidence_reconciliation"
    assert session.diagnosis.pass_history[0].live is True
    assert session.diagnosis.pass_history[0].deployment == "gpt-5.6-sol"
    assert session.diagnosis.pass_history[1].deployment == "gpt-5.6-terra"
    codes = {issue.code for issue in session.critique.issues}
    assert CritiqueCode.CROSS_CLAIM in codes
    assert session.stage.value == "human_strategic_lock"
    assert session.lock is None


def test_live_call_budget_fits_reasoning_plus_short_json():
    assert MAX_OUTPUT_TOKENS >= 4096
    assert NOTES_SCHEMA["properties"]["notes"]["maxLength"] == NOTES_MAX_LENGTH == 400


def test_parse_pass_notes_recovers_wrapped_json():
    wrapped = 'prefix {"notes":"GI-AE vs discontinuation","flagged_contradictions":["gi-ae"],"open_questions":[]} suffix'
    notes = parse_pass_notes(wrapped)
    assert notes.notes == "GI-AE vs discontinuation"
    assert notes.flagged_contradictions == ["gi-ae"]
    assert extract_json_object("truncated {\"notes\":\"no close") is None


class _Incomplete:
    def __init__(self, text: str, status: str, reason: str) -> None:
        self.output_text = text
        self.status = status
        self.incomplete_details = type("Details", (), {"reason": reason})()


def test_incomplete_truncated_json_is_an_error():
    try:
        notes_from_response(_Incomplete('{"notes":"cut', "incomplete", "max_output_tokens"))
    except ValueError as exc:
        assert "incomplete_response:max_output_tokens" in str(exc)
    else:
        raise AssertionError("expected incomplete_response")
