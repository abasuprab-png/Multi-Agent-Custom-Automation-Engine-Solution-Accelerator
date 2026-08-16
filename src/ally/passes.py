"""Two Ally passes. Sol thinks. Terra does. Both are frontier 5.6."""

from ally.contracts import PassConfig, PassRecord
from ally.enums import AllyPass
from ally.foundry_project import MODEL_DOING_DEPLOYMENT, MODEL_THINKING_DEPLOYMENT

DISCOVERY_COUNSEL = PassConfig(
    ally_pass=AllyPass.DISCOVERY_COUNSEL,
    temperature=0.35,
    thinking_budget="generous",
    work="thinking",
    deployment_name=MODEL_THINKING_DEPLOYMENT,
)

EVIDENCE_RECONCILIATION = PassConfig(
    ally_pass=AllyPass.EVIDENCE_RECONCILIATION,
    temperature=0.0,
    thinking_budget="tight",
    work="doing",
    deployment_name=MODEL_DOING_DEPLOYMENT,
)

PASS_CONFIGS = {
    AllyPass.DISCOVERY_COUNSEL: DISCOVERY_COUNSEL,
    AllyPass.EVIDENCE_RECONCILIATION: EVIDENCE_RECONCILIATION,
}


def pass_record(
    ally_pass: AllyPass,
    *,
    live: bool = False,
    error: str | None = None,
) -> PassRecord:
    config = PASS_CONFIGS[ally_pass]
    return PassRecord(
        ally_pass=ally_pass,
        model_tier=config.model_tier,
        temperature=config.temperature,
        thinking_budget=config.thinking_budget,
        work=config.work,
        deployment=config.deployment_name,
        live=live,
        error=error,
    )
