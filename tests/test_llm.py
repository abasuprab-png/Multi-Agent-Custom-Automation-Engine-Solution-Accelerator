"""Live LLM is env-gated. Injected fakes must not replace deterministic gates."""

from ally.enums import AllyPass, CritiqueCode
from ally.fixtures import gi_ae_contradiction_input
from ally.foundry_project import MODEL_DOING_DEPLOYMENT, MODEL_THINKING_DEPLOYMENT
from ally.llm import AllyPassNotes, NoOpAllyLLM, llm_enabled, llm_from_env
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


def test_pytest_default_is_noop_and_not_live():
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
