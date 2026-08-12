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

This slice does **not** call a live model, ClinicalTrials.gov, CAMS, or Lexie/RCC. It enforces the object model those tools will sit on. The GI-AE fixture is the eval: a planted contradictory draft must be caught, held, and handed to a human as a structured interrupt.

## Run

```bash
python -m pip install -e ".[dev]"
pytest
```

## Public API

```python
from ally import run_vertical_slice
from ally.fixtures import gi_ae_contradiction_input, happy_path_input

session, result = run_vertical_slice(gi_ae_contradiction_input())
assert result.stage.value == "human_strategic_lock"
assert result.handoff is not None
```
