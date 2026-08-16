# Wire ally-runtime onto Microsoft Foundry

This is the implementable control-plane map. It does not replace `ally-runtime`. It does not introduce a second Ally agent. It does not use Magentic, MACAE content packs, or prompt-routed multi-agent graphs.

Ally remains a sequence-locked state machine with typed objects. Foundry is the host, the model bill, and the observe plane.

## Decision (locked)

| Question | Answer |
| --- | --- |
| Agent type | **One Hosted agent** named `ally`, custom Python running `ally-runtime` |
| Protocol | **Invocations** (`POST /invocations`, protocol `1.0.0`) |
| Model | **One** Direct-from-Azure frontier reasoning deployment, used for both Ally passes |
| Passes | Discovery+Counsel at temperature `0.35` / generous thinking; Evidence Reconciliation at `0.0` / tight thinking |
| Human Strategic Lock | Invocations **interrupt**. `apply_lock` is a second call. Never auto-execute. |
| Lexie / RCC | Later Hosted agents that accept only `AgentHandoff` JSON. Not now. |
| Eval source of truth | Existing pytest + GI-AE fixture. Foundry observe/eval sits on top. |

Prompt agents are rejected. Foundry's default Agent Framework / Magentic path is rejected. Connected-agents / A2A free-text handoffs are rejected.

## Why hosted + Invocations (not prompt, not Responses)

Foundry has two agent types: prompt agents (instructions + tools, no application code) and hosted agents (your container, Foundry-managed endpoint, identity, sessions). See [What is Microsoft Foundry Agent Service?](https://learn.microsoft.com/en-us/azure/foundry/agents/overview) and [Hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents).

Ally already owns orchestration in code:

- six stages in `STAGE_ORDER`
- two internal passes, not two agents
- Pydantic contracts (`HumanInput`, `HumanHandoff`, `HumanStrategicLock`, `AgentHandoff`)
- quarantine on untagged input
- execution unreachable without a lock bound to `diagnosis.digest()`

A prompt agent cannot enforce any of that. Its only steering surface is a system prompt and tools. That is Magentic-shaped control, which this repo already replaced.

Hosted-agent protocols ([runtime contract](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agent-contract)):

| Protocol | Payload | Who owns state | Use for Ally? |
| --- | --- | --- | --- |
| **Responses** | OpenAI `/responses` chat items | Platform conversation history | No — control plane. Chat turns are untagged claims. |
| **Invocations** | Arbitrary JSON you define | You (`session_id` + store) | **Yes — control plane** |
| Invocations WebSocket | Bidirectional audio | You | No |
| A2A (preview) | Agent-to-agent text/tasks | Platform delegation | **Forbidden** for Lexie/RCC |
| Activity | Teams / M365 | Platform | Later, only as a UI shim over Invocations |

Invocations is the correct protocol because the platform is pass-through: it does not interpret the body, does not hydrate chat history, and does not invent an inter-agent message. That is required for forced behavior 5 (formal quarantine on agent-to-agent input).

A Hosted agent may expose both protocols at once. Do **not** add Responses in the first deploy. If a Teams surface is needed later, add Responses as a thin translator that only constructs `HumanInput` / `HumanStrategicLock` objects. Never let Responses conversation history become the diagnosis.

## How ally-runtime maps onto Foundry invoke

The adapter is already in `ally.foundry`. Foundry's gateway calls the container; the container calls `handle_invoke`.

```
Client
  POST {project}/agents/ally/endpoint/protocols/invocations
       ?agent_session_id=<id>
  body: AllyInvokeRequest
        ↓
Hosted container (port 8088, GET /readiness)
  azure-ai-agentserver-invocations
        ↓
handle_invoke(request, SessionStore)
        ↓
run_vertical_slice / AllySession.apply_lock / AllySession.enter_execution
        ↓
AllyInvokeResponse  (HumanHandoff | AgentHandoff | typed error)
```

Legal operations — there is no "chat" op:

| `op` | Input | Runtime call | Output | Auto-continue? |
| --- | --- | --- | --- | --- |
| `start` | `HumanInput` | `run_vertical_slice` | `HumanHandoff`, `interrupt=true`, stage `human_strategic_lock` | **No** |
| `apply_lock` | `session_id` + `HumanStrategicLock` | `session.apply_lock` | same stage, `interrupt=false` only after a valid lock | **No** |
| `enter_execution` | `session_id` + `to_agent` | `session.enter_execution` | `AgentHandoff` with required `lock` | Only after lock |

`apply_lock` does not enter execution. That is deliberate. The Human Strategic Lead signs; a separate, explicit call releases Lexie/RCC.

Session routing: Foundry Invocations reads `agent_session_id` from the **query string** only ([manage hosted sessions](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-sessions)). The body `session_id` is Ally's logical id. First deploy: set both to the same value. Persist `AllySession` under `$HOME` (restored after the 15-minute idle deprovision). Cosmos is later, when lock interrupts outlive sandbox files.

Container contract ([hosted agent runtime contract](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agent-contract)):

- listen on `0.0.0.0:8088` (plain HTTP; platform terminates TLS)
- `GET /readiness` → 200
- `POST /invocations`
- read `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL_NAME`, `FOUNDRY_AGENT_SESSION_ID`
- graceful `SIGTERM`

First-deploy host (not in this PR — no extra dependency yet):

```python
from starlette.requests import Request
from starlette.responses import JSONResponse
from azure.ai.agentserver.invocations import InvocationAgentServerHost
from ally.foundry import AllyInvokeRequest, SessionStore, handle_invoke

app = InvocationAgentServerHost()
STORE = SessionStore()

@app.invoke_handler
async def invoke(request: Request):
    payload = AllyInvokeRequest.model_validate(await request.json())
    return JSONResponse(handle_invoke(payload, STORE).model_dump(mode="json"))

if __name__ == "__main__":
    app.run()
```

## Human Strategic Lock on Foundry

Do not use LangGraph `interrupt()` + Responses `__hosted_agent_adapter_interrupt__`. That path belongs to a chat protocol we are not using.

Do not use Foundry connected-agents, routines, or "require approval" tool gates as a substitute for `HumanStrategicLock`. Those gates approve a model tool call. Ally's lock is an object-model constructor: `diagnosis_digest` + `signed_by` + `signature` + `closed_decision_ids`.

Mapping:

1. `start` always returns `interrupt=true` and a `HumanHandoff` (critique, quarantine, open decision points).
2. The client — a thin lock UI, not the Agents Playground chat — renders `open_decision_points`.
3. The lead posts `apply_lock` with a `HumanStrategicLock` whose `diagnosis_digest` matches `diagnosis.digest()`.
4. Wrong digest, missing closed decisions, or missing signature → `LockGateError`. Stage stays `human_strategic_lock`.
5. Only then may the client post `enter_execution`.

Signature in the first live slice: `signed_by` = Entra OID / UPN of the Human Strategic Lead (`x-agent-user-id` is available on container protocol 2.0.0). `signature` = opaque token the client obtained after the lead confirmed. Bind it to the digest in application code before calling `apply_lock`. Do not treat playground "thumbs up" as a lock.

## Lexie / RCC later — typed handoff only

`AgentHandoff.lock` is required by the schema. A missing lock is a `ValidationError`, not a warning.

When those agents exist:

- Each is its **own** Hosted agent (`lexie`, `rcc`) with Invocations only.
- The only legal body is `AgentHandoff`. Reject free text, Responses items, and A2A tasks.
- On ingest they run the same trust rule: untagged claims → quarantine.
- Ally does not call them through Foundry "connected agents" or A2A. Ally's container (or the client after lock) POSTs the `AgentHandoff` JSON to their `/invocations`.
- Do not create a second Ally agent that "plans" which specialist to call.

Until those containers exist, `enter_execution` still returns the typed object. That is enough to prove the gate.

## Model + project plan (credits)

Use models **sold directly by Azure**. Those draw Microsoft for Startups / sponsorship credits. Partner/Marketplace models do not. Anthropic Claude on Foundry is Marketplace CCU billing and is **not** supported on credit-only / sponsored subscriptions; a card on file is charged instead. See [Foundry model sponsorship coverage](https://learn.microsoft.com/en-us/startups/benefits/technical-benefits/azure-credits/foundry-model-sponsorship-coverage) and [Claude in Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-claude).

### Deploy this

| Item | Choice | Why |
| --- | --- | --- |
| Region | **East US 2** | Hosted agents are available; `gpt-5.2` Global Standard is listed for East US 2 ([region availability](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure-region-availability), [hosted agents](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)) |
| Project | New **Foundry (new)** project, not a classic hub project | Hub projects are limited to older models |
| Model | **One** deployment: `gpt-5.2` (2025-12-11), **Global Standard** | Frontier reasoning, Direct-from-Azure, pay-per-token. Same deployment for both passes. |
| SKU | Standard / Global Standard, **not** Provisioned (PTU) | PTU burns credits whether you run Ally or not |
| TPM | Start at **50k–100k TPM** | Vertical slice, not a swarm. Raise only if 429s appear. |
| Fallback if `gpt-5.2` is gated | `gpt-5` Global Standard, same region | Still Direct-from-Azure. Request GPT-5.x access if the catalog shows a lock. |
| Do not deploy | Claude, Grok, Llama, Mistral, extra GPT-5-mini "recon" deployment, image models | Credits and/or a second implicit agent |

Both Ally passes call this one deployment via the project's Responses API (`AIProjectClient` → `get_openai_client().responses.create`). Difference is parameters, not identity:

| Pass | Temperature | Thinking | `reasoning.effort` (when the API exposes it) |
| --- | --- | --- | --- |
| Discovery+Counsel | `0.35` | generous | `high` or `medium` |
| Evidence Reconciliation | `0.0` | tight | `low` |

Do not "save money" by sending reconciliation to a mini/nano model. The runtime contract is `model_tier="frontier_reasoning"` for both.

First hosted deploy may keep the current deterministic slice (no live LLM). That spends almost no inference credits and still proves Invocations + lock. Turn the model on in a second deploy once the invoke contract is green in Foundry.

### Credit hygiene (~$5k)

- One project, one model, one hosted agent.
- Hosted compute bills while a session is **active**; idle timeout is 15 minutes. Do not leave playground sessions open.
- No PTU reservation.
- No Marketplace models.
- No extra agents that provision sandboxes.
- Cap eval runs: GI-AE + happy path, not a 1k-row generic quality suite.
- Keep a reserve (~10%) for App Insights and mistakes.

## Resource list

### Provision now (first deploy)

| Resource | Purpose |
| --- | --- |
| Resource group `rg-ally-foundry-dev` | Single blast radius |
| Microsoft Foundry account + **one** project `ally` | Host + model endpoint |
| Model deployment `gpt-5.2` Global Standard | Both Ally passes |
| Hosted agent `ally` (Invocations 1.0.0) | Runs `ally-runtime` |
| Application Insights connected to the project | Server-side traces ([trace setup](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/trace-agent-setup)) |
| Log Analytics workspace (created with App Insights) | Trace store |

Deploy mode: **direct code / zip** (`codeConfiguration` in `azure.yaml`). Foundry builds the image. **Do not create ACR** until a Dockerfile is actually required. See [azure.yaml reference](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/azure-yaml-reference) and [What's new in Hosted Agents](https://devblogs.microsoft.com/foundry/hosted-agents-build26/).

### Provision later

| Resource | When |
| --- | --- |
| ACR | Only if the host needs a custom Dockerfile |
| Cosmos DB | When lock interrupts must survive `$HOME` eviction |
| Hosted agents `lexie`, `rcc` | After lock+handoff is proven |
| Live ClinicalTrials.gov HTTP client | After `StructuredRetriever` + fixture stay green |
| CAMS / Canon store | After in-package Canon ADM-1/ADM-2 is insufficient |
| BYO VNet / private ACR | Compliance, not the vertical slice |

### Do not create

- Magentic / Microsoft Agent Framework multi-agent workflow as the control plane
- MACAE content packs, Cosmos chat collections, or the accelerator's agent swarm
- Prompt agents named Ally, Counsel, Reconciliation, or Manager
- Foundry connected-agents / A2A between Ally and anyone
- A second Ally agent
- Toolbox packed with web search as implicit ground truth
- Agent Optimizer rewriting `SYSTEM_PROMPT` (it can weaken SEQUENCE LOCK)
- Extra model deployments "for specialists"
- Image / speech / voice-live resources

## Risks if we use Foundry "multi-agent" primitives

| Primitive | What it does | How it breaks Ally |
| --- | --- | --- |
| Prompt agent | Model + instructions + tools | Sequence lock becomes a suggestion. Untagged tool output is ingested as fact. |
| Connected agents | Manager delegates by conversation | Free-text handoff. `AgentHandoff.lock` never constructed. |
| A2A | Agent-to-agent task protocol | Same: text, not objects. Quarantine bypassed. |
| Magentic / Agent Framework group chat | LLM-planned routing | The rejected foundation. Stages become a ledger the model edits. |
| Responses conversation history | Platform hydrates prior turns | Human/web/account turns enter without `verified\|inferred\|unresolved`. |
| Routines / agent optimizer | Platform rewrites behavior | Admissibility and lock become prompt flavor. |
| Playground "run" | Chat completion loop | Looks like success while skipping Human Strategic Lock. |

Foundry docs themselves describe Agent Service connected-agent workflows as primarily **nondeterministic** ([AI agent design patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)). Ally is the opposite: a lock.

## Eval plan

**Source of truth stays pytest.** The GI-AE fixture is the eval. Foundry does not replace `tests/test_vertical_slice.py`.

Layers ([test a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/test-hosted-agent)):

| Layer | Tool | What it proves |
| --- | --- | --- |
| 1. Object contracts | `pytest` (existing + `tests/test_foundry_invoke.py`) | Five forced behaviors; unsigned execution impossible |
| 2. Local invoke | `handle_invoke` against GI-AE / happy path | Invocations ops do not auto-execute |
| 3. Deployed invoke | `azd ai agent invoke -p invocations` with the same JSON | Container + gateway preserve the blob |
| 4. Foundry eval (thin) | `azd ai agent eval` dataset = serialized `gi_ae_contradiction_input()` | Same assertions, visible in Control Plane |
| 5. Traces | App Insights / Foundry tracing | Two pass spans, quarantine events, lock interrupt. Not quality scores. |

Foundry built-in evaluators (groundedness, similarity, coherence) are **not** the gate. A fluent inadmissible lede can score well and still fail ADM-1. If a Foundry eval recipe is added, custom checks must assert:

- `stage == human_strategic_lock` after `start`
- `agent_handoff is None` until `apply_lock` + `enter_execution`
- GI-AE critique codes include `cross_claim`, both admissibility codes, `genre`, `estimand`, `intensifier`
- quarantine is non-empty
- `enter_execution` without lock returns `LockGateError`

Do not convert production traces into a generic chat dataset and "optimize" the prompt. Traces are evidence for the Human Strategic Lead, not training data for a manager agent.

## First PR / first deploy scope

### This PR (no Azure spend)

- Keep `ally-runtime` as the package.
- Add `ally.foundry` Invocations types + `handle_invoke`.
- Add pytest that the GI-AE case still dies at the lock through Foundry ops.
- This document.

### First deploy (credits: project + traces + optional zero-token host)

1. Create Foundry project in East US 2; connect App Insights.
2. Deploy **one** `gpt-5.2` Global Standard (or skip the model if hosting the deterministic slice first).
3. Add a thin `InvocationAgentServerHost` wrapper (new small package extra). Zip-deploy Hosted agent `ally`, Invocations only.
4. Invoke GI-AE JSON against the cloud endpoint. Confirm interrupt. Confirm unsigned `enter_execution` fails.
5. Stop. Do not add Lexie, RCC, CT.gov HTTP, CAMS, ACR, Cosmos, Teams, or a second model.

### Next PRs (ordered)

1. Live LLM port: same `PassConfig`, `AIProjectClient` Responses calls, structured output into existing Pydantic types. pytest still uses fixtures when `FOUNDRY_PROJECT_ENDPOINT` is unset.
2. `$HOME` session persistence so a lock can be applied after idle.
3. Lock UI that posts `HumanStrategicLock` (Entra-bound `signed_by`).
4. Lexie/RCC Hosted agents that validate `AgentHandoff`.
5. Live `StructuredRetriever` behind the existing port.

## azure.yaml shape (first deploy, do not apply yet)

```yaml
requiredVersions:
  azd: ">=1.27.1"
  extensions:
    azure.ai.agents: ">=1.0.0-beta.8"
    azure.ai.projects: ">=1.0.0-beta.4"

services:
  ally-project:
    host: azure.ai.project
    location: eastus2

  ally-gpt52:
    host: azure.ai.model
    model: gpt-5.2
    deploymentType: GlobalStandard

  ally:
    host: azure.ai.agent
    kind: hosted
    project: src
    protocols:
      - protocol: invocations
        version: 1.0.0
    codeConfiguration:
      runtime: python
      entryPoint: ally.foundry_host:app
```

Exact field names follow the current [azure.yaml reference](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/azure-yaml-reference) at deploy time. Do not add `toolbox`, `skill`, `routine`, or a second `azure.ai.agent` service in that file.

## Non-goals (repeat)

- Do not start over.
- Do not restore Magentic / MACAE as the foundation.
- Do not invent a second Ally agent.
- Do not put Evidence Reconciliation on a cheaper model.
- Do not auto-execute after critique "passes".
- Do not hand Lexie/RCC a paragraph.
