"""Two Ally passes. Same tier. Reconciliation is colder, not cheaper."""

from ally.contracts import PassConfig, PassRecord
from ally.enums import AllyPass

DISCOVERY_COUNSEL = PassConfig(
    ally_pass=AllyPass.DISCOVERY_COUNSEL,
    temperature=0.35,
    thinking_budget="generous",
)

EVIDENCE_RECONCILIATION = PassConfig(
    ally_pass=AllyPass.EVIDENCE_RECONCILIATION,
    temperature=0.0,
    thinking_budget="tight",
)

PASS_CONFIGS = {
    AllyPass.DISCOVERY_COUNSEL: DISCOVERY_COUNSEL,
    AllyPass.EVIDENCE_RECONCILIATION: EVIDENCE_RECONCILIATION,
}


def pass_record(ally_pass: AllyPass) -> PassRecord:
    config = PASS_CONFIGS[ally_pass]
    return PassRecord(
        ally_pass=ally_pass,
        model_tier=config.model_tier,
        temperature=config.temperature,
        thinking_budget=config.thinking_budget,
    )
