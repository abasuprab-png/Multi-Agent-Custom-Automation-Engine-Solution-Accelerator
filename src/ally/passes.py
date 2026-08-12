"""Two Ally passes. Same tier. Reconciliation is colder, not cheaper."""

from ally.contracts import PassConfig
from ally.enums import AllyPass, Stage

DISCOVERY_COUNSEL = PassConfig(
    ally_pass=AllyPass.DISCOVERY_COUNSEL,
    stages=(Stage.DISCOVERY, Stage.COUNSEL),
    temperature_min=0.3,
    temperature_max=0.4,
    thinking_budget="generous",
)

EVIDENCE_RECONCILIATION = PassConfig(
    ally_pass=AllyPass.EVIDENCE_RECONCILIATION,
    stages=(Stage.EVIDENCE_RECONCILIATION,),
    temperature_min=0.0,
    temperature_max=0.1,
    thinking_budget="tight",
)

PASS_CONFIGS = {
    AllyPass.DISCOVERY_COUNSEL: DISCOVERY_COUNSEL,
    AllyPass.EVIDENCE_RECONCILIATION: EVIDENCE_RECONCILIATION,
}


def temperature_for(ally_pass: AllyPass) -> float:
    """Deterministic pick inside the configured window. Reconciliation uses the floor."""
    config = PASS_CONFIGS[ally_pass]
    if ally_pass is AllyPass.EVIDENCE_RECONCILIATION:
        return config.temperature_min
    return (config.temperature_min + config.temperature_max) / 2
