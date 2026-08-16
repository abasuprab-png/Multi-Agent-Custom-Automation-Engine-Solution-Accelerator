# Ally runtime

Typed multi-agent runtime for strategic counsel. Magentic-style prompt routing is not the control plane. Every section exists to force one of five behaviors:

1. **Outside-in verification** — human, web, and agent claims take the same `verified` / `inferred` / `unresolved` tag. Untagged input is quarantined.
2. **Doctrine as an executable filter** — Admissibility is a checklist against citable Canon rules ADM-1 and ADM-2. Unanswered is a no.
3. **Cross-claim consistency** — Evidence Reconciliation is a second, colder pass. The planted GI-AE / discontinuation contradiction cannot reach execution unsigned.
4. **Genre-convention knowledge** — approval-release ledes are checked against a curated set. Atmosphere is not a completed regulatory action.
5. **Quarantine on agent-to-agent input** — handoffs are objects. Lexie/RCC cannot be constructed with a diagnosis that lacks a Human Strategic Lock signature.

## Six stages

1. `discovery`
2. `counsel`
3. `structured_retrieval`
4. `evidence_reconciliation`
5. `human_strategic_lock`
6. `execution` — unreachable without a lock signature bound to the diagnosis digest

Ally is two internal passes, not two agents: Discovery+Counsel (temp 0.3–0.4) and Evidence Reconciliation (temp 0–0.1, same frontier tier).

This slice does **not** call a live model, CAMS, or Lexie/RCC. Structured retrieval is a port (`StructuredRetriever`); the ClinicalTrials.gov fixture is what resolves REDEFINE-style estimand confusion. Identity inference is read from prose. Cross-claim rules live in a registry. The GI-AE fixture remains the eval for unsigned execution.

## Foundry (host, not control plane)

Microsoft Foundry hosts **one** Invocations agent that calls `handle_invoke`. It does not become a prompt agent, Magentic graph, or second Ally. Human Strategic Lock is an interrupt: `start` returns `HumanHandoff`; `enter_execution` is unreachable until `apply_lock`. See [docs/foundry-ally-architecture.md](docs/foundry-ally-architecture.md).

Target project (already exists — do not create a second account):

- Subscription `85d4d146-1694-46a2-9830-43ec9f2c5ba2`
- Resource group `sfg-commsos-prod`
- Account `commsos-foundry-hub`
- Project `CommsOS-Core`
- Endpoint `https://commsos-foundry-hub.services.ai.azure.com/api/projects/CommsOS-Core`

Local host (no Azure credentials, no model):

```bash
python3 main.py
# GET  http://127.0.0.1:8088/readiness
# POST http://127.0.0.1:8088/invocations
```

Writer craft from the regulated-wire-editor doctrine is `review_draft()`. Findings never block. Deterministic gates stay in the claim pipeline.

Deploy to the existing project (after Azure login):

```bash
azd env set AZURE_SUBSCRIPTION_ID 85d4d146-1694-46a2-9830-43ec9f2c5ba2
azd env set AZURE_AI_PROJECT_ENDPOINT https://commsos-foundry-hub.services.ai.azure.com/api/projects/CommsOS-Core
azd ai agent deploy
```

## Run

```bash
python -m pip install -e ".[dev]"
pytest
```

## Public API

```python
from ally import run_vertical_slice
from ally.fixtures import gi_ae_contradiction_input, happy_path_input

session = run_vertical_slice(gi_ae_contradiction_input())
assert session.stage.value == "human_strategic_lock"
assert session.lock is None
```
