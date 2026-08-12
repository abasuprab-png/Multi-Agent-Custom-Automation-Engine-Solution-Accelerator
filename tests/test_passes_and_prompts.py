"""Prompt sections exist so the LLM can be wired later. Runtime is the enforcer."""

from ally.enums import STAGE_ORDER, AllyPass
from ally.fixtures import happy_path_input
from ally.passes import DISCOVERY_COUNSEL, EVIDENCE_RECONCILIATION
from ally.prompts import REQUIRED_SECTION_HEADINGS, SYSTEM_PROMPT
from ally.runtime import run_vertical_slice


def test_required_prompt_sections_are_present():
    for heading in REQUIRED_SECTION_HEADINGS:
        assert heading in SYSTEM_PROMPT
    for stage in STAGE_ORDER:
        assert stage.value in SYSTEM_PROMPT


def test_reconciliation_is_same_tier_colder_not_cheaper():
    assert DISCOVERY_COUNSEL.model_tier == EVIDENCE_RECONCILIATION.model_tier == "frontier_reasoning"
    assert EVIDENCE_RECONCILIATION.temperature_max <= 0.1
    assert DISCOVERY_COUNSEL.temperature_min >= 0.3
    assert EVIDENCE_RECONCILIATION.thinking_budget == "tight"
    assert DISCOVERY_COUNSEL.thinking_budget == "generous"


def test_slice_records_both_passes():
    _, result = run_vertical_slice(happy_path_input())
    assert result.diagnosis is not None
    passes = [record.ally_pass for record in result.diagnosis.pass_history]
    assert AllyPass.DISCOVERY_COUNSEL in passes
    assert AllyPass.EVIDENCE_RECONCILIATION in passes
    recon = next(
        record
        for record in result.diagnosis.pass_history
        if record.ally_pass is AllyPass.EVIDENCE_RECONCILIATION
    )
    assert recon.temperature <= 0.1
    assert recon.model_tier == "frontier_reasoning"
