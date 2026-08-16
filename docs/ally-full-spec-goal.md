# Ally full-spec goal (working brief)

This is the statement to work against. It is the original spec, not the first-deploy stop line.

## Goal

Build Ally as a sequence-locked state machine with typed objects. Foundry is the host, the model bill, and the observe plane. Do not start from Magentic. Do not add a second Ally agent. Do not use Claude or any Marketplace model.

Ally is **one** Hosted agent (`ally`) on existing `commsos-prod`, **Invocations only**. Ally is **two internal passes**, not two agents:

| Pass | Maps to | Deployment | Work | Temp | Thinking |
| --- | --- | --- | --- | --- | --- |
| Discovery+Counsel | stages 1–2 | `gpt-5.6-sol` | thinking | 0.35 | generous / `high` |
| Evidence Reconciliation | stage 4 | `gpt-5.6-terra` | doing | 0.0 | tight / `low` |

Both stay `model_tier="frontier_reasoning"`. Do not downgrade reconciliation. Deterministic gates stay authoritative after any LLM output. LLM notes must not rewrite verified claims or replace critique.

## Required object-model behavior

1. Six stages in code: discovery → counsel → structured_retrieval → evidence_reconciliation → human_strategic_lock → execution.
2. One trust rule, three sources. Human / web / agent all require `verified | inferred | unresolved`. Untagged → quarantine.
3. Admissibility is ADM-1 / ADM-2, citable, executable. Either no → inadmissible.
4. Genre convention is a checker plus a retrievable approval-release library, not inferred register.
5. No efficacy percentage without estimand basis (`trial_product | treatment_policy | treatment_regimen`).
6. Intensifiers only with a cited number in the same sentence.
7. Vocab firewall gates retrieval and output. The prompt names the filter; it does not substitute for it.
8. Refusal is designed: missing client/brand/lead/task refuses. Lazy answers are push-back, not completion.
9. Human Strategic Lock is a hard gate. `apply_lock` does not auto-execute. Unsigned `enter_execution` throws `LockGateError`. Lexie/RCC cannot receive a diagnosis lacking a lock signature.
10. Every inter-agent handoff is a structured object with explicit `unresolved[]` and `inferred[]`. Free text is illegal.

## Required tools (code, not prompt hope)

- Web search + fetch for outside-in discovery. Hits land as tagged envelopes, never as ground truth.
- ClinicalTrials.gov + openFDA behind `StructuredRetriever`. Primary records supersede estimand-less press paraphrase.
- Canon / Doctrine retrieval that returns citable rule IDs.
- Genre library retrieval, tagged by type.
- CAMS **read only**. Write stays behind the lock. No CAMS write API exists in this runtime.
- Typed diagnosis emission (`AllyStrategicDiagnosis`).
- Self-critique checklist (already a code gate; keep it).
- Human handoff object (already an Invocations interrupt; keep it).
- Delegation brief: downstream agents may not infer identity or facts beyond what is stated.
- Lock UI that posts `HumanStrategicLock` bound to `diagnosis.digest()`.
- Hosted-shaped Lexie and RCC handlers that accept only `AgentHandoff`.

## Memory

- Short-term: running diagnosis and open-verification persist across idle (`$HOME`).
- Long-term: correction-pattern store, partitioned by `client_id` / `brand_id`.
- Per-lead notes are silent. They never override an honest disagreement.
- Every lock that closes Ally's decision points records a correction category. The metric is that a category stops recurring, not that a transcript is memorized.

## Execution models

Lexie/RCC may call a cheaper model **only** when `ALLY_EXECUTION_ABLATION=1`. Default is validate-the-handoff, not a cheap-model assumption.

## Eval — a slice is not done until

- Pytest + GI-AE still die at the lock.
- Unsigned execution still throws.
- Live or fixture primary retrieval supersedes estimand-less secondary percentages.
- Lock UI can sign and still not auto-execute.
- Lexie/RCC reject free text and unsigned diagnoses.
- Competitive landscape is never baked into a prompt or fine-tune.

## Non-goals

- Magentic / MACAE content packs as the control plane.
- Prompt-locked sequences.
- Free-text inter-agent messages.
- A second Ally agent.
- Claude / Marketplace CCU models.
- A second Foundry account.
- Auto-execute after critique "passes".
