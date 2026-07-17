# Company Command: Strategy for a Reusable Autonomous-Company Framework

**Status:** Recommended direction

**Date:** 2026-07-15

**Tracking:** [Company Command issue #1](https://github.com/advatar/Company Command/issues/1)

**Evidence cutoff:** 2026-07-15

## Executive decision

Build Company Command as a small, model-neutral company control plane. Do not adopt MandamusCo wholesale, and do not make Claude Cowork, ChatGPT Work, Codex, Paperclip, CrewAI, or any other agent product the system of record.

The first version should compile a declarative CompanySpec into durable work, run that work through replaceable agent workers, mediate every side effect through a deterministic capability gateway, and pause durably for authenticated human approval when policy requires it. Roles should be bundles of skills, permissions, data scopes, model policies, budgets, and escalation rules—not fictional employees sustained by long group-chat transcripts.

The recommended first stack is:

- Python, Pydantic, and FastAPI for the company kernel and typed contracts.
- [DBOS](https://docs.dbos.dev/) on Postgres for the first durable workflow runtime.
- Postgres as the source of truth, with full-text search and pgvector only where evaluation shows a retrieval benefit.
- S3-compatible object storage for large artifacts.
- A narrow Worker API with adapters for a simple tool-using agent, Codex App Server, and OpenHands.
- An OpenAI-compatible Model API, served locally by [vLLM](https://docs.vllm.ai/en/latest/serving/online_serving/openai_compatible_server/), [SGLang](https://docs.sglang.io/), or [llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md), plus optional hosted fallbacks. A Codex route is enabled only for servers that pass the required Responses-API conformance suite.
- A WebAuthn-authenticated action-approval service. Synced passkeys may be accepted where the risk assessment permits AAL2-style authentication and the sync-fabric requirements are met. Tiers requiring non-exportability or independent custody should use verified high-assurance authenticator policy and, for truly consequential actions, distinct-person dual control.

DBOS is the better starting point because its open-source library supplies durable execution, queues, events, and human waits on Postgres. Production high availability still needs an explicit recovery/operations design, potentially including DBOS Conductor. Temporal is a later candidate—not a predetermined destination—if measured reliability, operations, or workflow requirements exceed DBOS. Workflow histories are not portable between the engines, so a migration would drain old runs and start new executions from Company Command business state. Do not operate DBOS and Temporal as competing owners of the same workflow.

### Direct answers

| Question | Answer |
|---|---|
| How does Claude Cowork work? | Public evidence describes a real agent harness: planning, an agent loop, code execution in isolated environments, parallel subagents, skills/plugins, connectors, permissions, and long-running state. |
| Is Cowork using role-specific fine-tuned models? | There is no public evidence of separately fine-tuned “finance,” “legal,” or “marketing” employee models. Anthropic’s own role plugins are Markdown and JSON bundles of skills, connectors, commands, and subagents. Internal routing or safety classifiers may exist, but occupational specialization is publicly implemented as context and tools. |
| Is it only RAG and prompt theater? | No. The persona layer is largely prompts, skills, and retrieved context, but the execution, isolation, orchestration, permission, artifact, and scheduling layers are substantive. Copy the harness engineering, not the office role-play. |
| Is Codex a better harness? | Codex is an excellent coding and repository worker, and its open-source CLI can use local providers. It is not a durable company scheduler, approval authority, or business ledger. Use it behind Company Command’s Worker API. |
| Do we need Mandamus? | No. Extract its canonical action intents, default-deny gate, approval state machine, scoped capabilities, and receipts. Leave its broader platform, liveness coupling, simulated approvals, and company-specific UI behind. |
| Is iProov Liveness required? | No for routine approvals. Correctly implemented WebAuthn resists verifier-impersonation phishing, but it does not protect a compromised Company Command origin, browser, session, or deceptive same-origin UI. High-assurance actions need an approved authenticator policy, short expiry, immutable action binding, conditional commit, and often distinct-person dual control. Liveness/PAD may be one component of identity proofing or exceptional recovery, not transaction authorization. |
| Does an extra personal PIN make a passkey stronger? | Usually not. A passkey with trusted user verification can combine authenticator possession with local PIN or biometric activation. PIN and biometric are normally alternatives, not two independent added factors. A server-verified application PIN can add a knowledge factor, but remains phishable and does not prove another device or person or improve WebAuthn’s phishing resistance. |

## 1. Define the product correctly

An autonomous company framework should not primarily simulate conversations between a CEO, CFO, CTO, and employees. It should instantiate a governed production system that converts goals into reviewable work and controlled effects.

The unit of operation is:

> goal → workflow → task → artifact or action intent → policy decision → verified effect → evidence

Chat can be an operator interface, but it must not be the authoritative workflow state. An org chart can explain responsibility, but it must not be the scheduler. A role prompt can bias behavior, but it must not grant authority.

### Design principles

1. **Deterministic kernel, agentic pockets.** Code owns state transitions, budgets, permissions, retries, deadlines, and commits. Models handle ambiguous interpretation, synthesis, planning within bounds, and artifact generation.
2. **One agent before many.** Add parallel workers only when tasks are independent, use meaningfully different tools or data, or provide measurable verification diversity.
3. **Intent is not authority.** A model may propose an action. Only the gateway can authorize and execute it.
4. **Artifacts over chat.** Agents hand off typed artifacts, claims with provenance, and task state—not an ever-growing shared transcript.
5. **Least privilege by construction.** Each worker receives a short-lived, task-scoped capability. It never receives master credentials.
6. **Durability before autonomy.** Every long-running task, retry, timer, human wait, and cancellation must survive process restarts.
7. **Provider neutrality at the boundary.** Company definitions select capability profiles, not vendor model names.
8. **Evaluation is part of the company pack.** A role or workflow is incomplete without tests and measurable exit criteria.
9. **Human attention is a bounded resource.** Approval queues require deduplication, priority, expiry, delegation, and clear consequence previews.
10. **Fail closed.** Provider failure, malformed output, missing policy, stale approval, or ambiguous external state must defer or reject—not trigger a canned business action.

## 2. What the two existing implementations actually provide

### 2.1 MandamusCo

MandamusCo is best understood as an authority and audit control plane accompanied by partly disconnected company demos. Its own product requirements state that it is not a general agent runtime or LLM orchestration framework.

The useful core is in its control plane:

- deterministic action tiers and policy gates;
- mandates and scoped capabilities;
- pending approvals and bounded escalation;
- action and operations receipts;
- tenant scoping and API-key separation;
- provenance-bound memory writes;
- hash-chained audit evidence.

The company implementation is not yet generic:

- role lists are hardcoded and differ across the UI, upstream service, and governed fleet;
- the fleet loop is sequential and lacks durable workflow semantics;
- mandates are seeded imperatively rather than compiled from a company manifest;
- the business UI stores important state in browser local storage;
- the main upstream uses one Claude model with role prompts;
- fallback paths can silently select canned actions after provider errors;
- approval demos accept placeholder values rather than verifying cryptographic assertions;
- the normal approval route does not consistently carry a WebAuthn assertion;
- the durable memory and vector retrieval described by the design are not fully wired.

Representative local evidence:

- <code>docs/PRODUCT-REQUIREMENTS-SPEC.md:104</code>
- <code>control-plane/src/gate.mjs:46-55</code>
- <code>control-plane/src/mandate.mjs:15-123</code>
- <code>control-plane/src/ops-receipt.mjs:95-118</code>
- <code>control-plane/src/agent-runtime.mjs:23-247</code>
- <code>control-plane/src/interagent.mjs:36-170</code>
- <code>control-plane/src/memory.mjs:35-130</code>
- <code>LandingPage/src/lib/passkey.ts</code>
- <code>docs/PLATFORM-SPEC.md:283</code>

**Decision:** do not make Company Command depend on Mandamus. Reimplement or extract a small “Mandamus Lite” policy package only after checking license compatibility. Preserve the concepts and tests, change missing policy to default-deny, replace liveness-specific assurance with a generic verifier interface, and remove simulated success paths.

### 2.2 autonomous-steam-studio

AutoSteam is a deterministic game-production pipeline wrapped in Claude/Codex skills and MCP tools. Most named “agents” are Python functions with typed inputs and outputs, not independently running models. This is not a defect; it is the strongest reusable design choice in the project.

Reusable strengths:

- Pydantic domain contracts and deterministic scoring;
- artifact-first handoffs;
- narrow MCP tools rather than unrestricted shell access;
- workspace confinement and credential stripping;
- evidence-producing QA and rule-based compliance;
- an explicit boundary between preparing a release and performing privileged store actions;
- cross-host skills and plugin packaging.

Current gaps:

- no durable scheduler, retries, leases, compensation, or human-wait state;
- no dynamic role instantiation or company manifest;
- no model router or open-model configuration;
- declared Postgres, Qdrant, and object storage are not connected to the core;
- approval flags are not backed by user identity or cryptographic authorization;
- market and compliance gates do not consistently prevent downstream work;
- the dashboard is sample data rather than a control-plane view.

Representative local evidence:

- <code>studio_core/orchestrator.py:15-43</code>
- <code>studio_core/agents/base.py:7</code>
- <code>studio_core/compliance/packet.py:30-75</code>
- <code>studio_core/release/readiness.py:26</code>
- <code>docs/ARCHITECTURE.md:20-28</code>
- <code>docs/ROADMAP.md:41</code>
- <code>plugins/autosteam-studio/runtime/autosteam_plugin_runtime/server.py:263-524</code>

**Decision:** make AutoSteam the first CompanyPack. Preserve its typed, deterministic domain kernel and keep pure function calls in-process; replace orchestration only at durable business boundaries with Company Command workflows. Place privileged actions behind Company Command’s gateway, and keep game-specific roles, schemas, skills, tools, and evaluations inside the pack.

### 2.3 Extraction summary

| Concern | MandamusCo | AutoSteam | Company Command decision |
|---|---|---|---|
| Roles | Hardcoded prompt identities | Named deterministic functions plus host prompts | Compile roles from CompanySpec |
| Workflow | Sequential demo loop | Synchronous pipeline | Durable typed state machine |
| Authority | Sophisticated gate and receipts | Policy comments and booleans | Reuse Mandamus concepts in a smaller default-deny gateway |
| Domain logic | Mostly demo company behavior | Strong deterministic game kernel | Domain logic belongs in CompanyPacks |
| Memory | Good provenance concept, incomplete durability | File-first; vector services unwired | Postgres truth, artifact store, derived retrieval |
| Models | Claude-centric upstream; raw provider demos | Core model-free; Codex shell | Provider-neutral Model and Worker APIs |
| Human approval | Broad design, mock/incomplete verification | Unauthenticated flags | WebAuthn-bound action approval |

## 3. Claude Cowork: documented architecture and honest inference

Anthropic’s current documentation says Cowork:

- analyzes a request and creates a plan;
- decomposes complex work;
- runs code and shell commands in an isolated environment;
- coordinates parallel subagents;
- exposes progress and steering;
- persists remote sessions and supports scheduled work;
- uses skills, plugins, MCP/connectors, folder instructions, and project context;
- requires explicit permission for destructive file deletion and offers manual, automatic safety review, and skip modes.

See [Get started with Claude Cowork](https://support.claude.com/en/articles/13345190-get-started-with-claude-cowork) and the [Cowork architecture overview](https://support.claude.com/en/articles/14479288-claude-cowork-architecture-overview). Remote sessions use isolated, temporary Anthropic-managed sandboxes with proxy-enforced egress and short-lived session tokens; connector authorization tokens remain server-side. The local architecture separates the native agent loop from code execution in a dedicated VM.

Anthropic also publishes its [knowledge-work plugins](https://github.com/anthropics/knowledge-work-plugins). Finance, legal, marketing, sales, operations, and other role packs are file-based Markdown and JSON. Each bundles skills, connectors, commands, and sometimes subagents. This is direct evidence for contextual specialization rather than one fine-tuned occupational model per role.

Anthropic’s containment write-up identifies three security layers: environment, model, and external content. It explicitly mentions system prompts, classifiers, probes, and training modifications at the model layer, and says tool results can be inspected by a smaller classifier before entering the main model context. See [How we contain Claude across products](https://www.anthropic.com/engineering/how-we-contain-claude).

### What can and cannot be concluded

**Documented:**

- a substantive execution and orchestration harness;
- general Claude model selection plus skills, instructions, tools, and project knowledge;
- separate safety/classifier machinery;
- sandbox and network enforcement outside the model;
- parallel subagent support.

**Not publicly documented:**

- a separately fine-tuned model for each business role;
- the exact planning prompt, router, compaction strategy, or subagent scheduler;
- whether hidden internal routing chooses specialized model checkpoints for some tasks;
- exact RAG indexing and ranking internals.

**Best inference:** Cowork roles are primarily the same family of general models configured by prompts, skills, context, connectors, and tool permissions. It is wrong to dismiss Cowork as “just RAG,” because the reliable value sits in execution isolation, durable task operation, parallelism, permissioning, and artifact production. It is also wrong to infer genuine professional expertise merely from a role name.

### Fine-tuning policy for Company Command

Do not fine-tune one model per role at launch. Begin with:

1. a role contract and evaluated skills;
2. scoped tools and data;
3. retrieval with provenance;
4. structured outputs;
5. deterministic validators;
6. a model profile selected by task evaluations.

Fine-tune only when there is a stable, repeated error class, a meaningful labeled dataset, a held-out evaluation, and evidence that prompt/tool/retrieval changes cannot achieve the target. The fine-tuned model must remain replaceable behind the same profile.

## 4. Codex, ChatGPT Work, and the worker-harness question

The current OpenAI product names matter. [ChatGPT Work](https://learn.chatgpt.com/docs/use-chatgpt#choose-how-you-want-to-work) targets substantial research and reviewable deliverables. Codex targets software and technical tasks. Neither is a self-hosted autonomous-company control plane.

Codex is nevertheless a strong Company Command worker:

- the CLI is [Apache-2.0 open source](https://github.com/openai/codex);
- it supports repository instructions, skills, plugins, MCP tools, hooks, sandboxing, approvals, subagents, and programmatic App Server use;
- the [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference#configtoml) documents Ollama and LM Studio OSS modes and custom model providers;
- custom backends can be used through an OpenAI-compatible Responses API;
- local execution provides a reviewable working tree and test loop.

OpenAI’s [Symphony](https://openai.com/index/open-source-codex-orchestration-symphony/) is the closest relevant reference pattern. It treats an issue tracker as the work state machine, gives every eligible ticket an isolated workspace and worker, applies bounded concurrency and retries, and hands results to human review. Its [specification](https://github.com/openai/symphony/blob/main/SPEC.md) deliberately does not mandate a universal approval or sandbox policy, and OpenAI describes it as an intentionally minimal reference rather than a maintained product.

### Recommendation

Use:

- **Codex App Server** for repository engineering, technical research, and artifact work where its tools fit.
- **OpenHands** as a model-neutral open-source coding worker, especially when container isolation and backend freedom matter. Its [runtime architecture](https://docs.openhands.dev/openhands/usage/architecture/runtime) separates the agent backend from a Docker action-execution server.
- **A small native agent worker** for non-coding business workflows. This should be a bounded tool loop with structured output, not a general multi-agent framework.
- **ChatGPT Work or Claude Cowork** as optional operator workspaces, never as Company Command’s source of truth.

Do not use any of them for:

- the canonical task ledger;
- durable cross-worker workflow state;
- business authorization;
- passkey verification;
- organization-wide budgets;
- the immutable audit record.

Codex is more suitable than Mandamus as a worker harness. Mandamus is more relevant than Codex as inspiration for authority controls. Company Command needs both concerns, but owns the boundary between them.

## 5. State of the art beyond frontier-lab products

### 5.1 Control planes and workflow engines

| Project | Best use in Company Command | Decision and caution |
|---|---|---|
| [Paperclip](https://github.com/paperclipai/paperclip) | Closest open-source product analogy: companies, goals, org charts, tasks, heartbeats, budgets, approvals, adapters | Use as a competitive benchmark, not the initial foundation. Before 2026.416.0, an agent-key-to-host RCE ([CVE-2026-41208](https://nvd.nist.gov/vuln/detail/CVE-2026-41208)) and a separate [critical unauthenticated RCE chain](https://github.com/paperclipai/paperclip/security/advisories/GHSA-68qg-g8mg-6pr7) involving signup, CLI approval, and import authorization exposed immature trust boundaries; both were patched in 2026.416.0. Evaluate the current release, recovery, authorization, configuration ownership, deployment defaults, license, and migration cost rather than extrapolating only from historical CVEs. |
| [Temporal](https://docs.temporal.io/) | Long-running production workflows, retries, timers, Signals/Updates, compensation, multi-service reliability | Keep as a candidate if measured reliability, operational, or workflow requirements exceed the DBOS design. It is not a drop-in backend swap: drain existing DBOS histories and start Temporal executions from Company Command business state. |
| [DBOS](https://docs.dbos.dev/) | Lightweight durable workflows, queues, events, and human waits on Postgres | Recommended MVP backbone. Its [HITL pattern](https://docs.dbos.dev/ai/hitl) durably waits with send/receive primitives. Cross-executor recovery and production operations still require an explicit design. |
| [LangGraph](https://docs.langchain.com/oss/python/langgraph/overview) | Complex stateful reasoning inside one task, checkpoints, interrupts, inspection and replay | Optional inside a worker. Do not let it and DBOS both own the business workflow. |
| [AutoGen](https://microsoft.github.io/autogen/stable/index.html) / [AG2](https://docs.ag2.ai/) | Multi-agent prototypes, event-driven agents, conversational handoffs | Useful research toolkit, not the company ledger. Prefer run-to-boundary then persist state; in-run human input can leave a team awkwardly suspended. |
| [CrewAI](https://docs.crewai.com/) | Fast role and workflow prototypes | If used, prefer structured Flows. Free-form crews and backstories encourage role theater. |
| [MetaGPT](https://github.com/FoundationAgents/MetaGPT) / [ChatDev](https://github.com/OpenBMB/ChatDev) | Company templates, SOP-as-code, declarative workflow inspiration | Borrow specification ideas; do not treat their software-company personas as a security or durability layer. |
| [OpenHands](https://github.com/All-Hands-AI/OpenHands) | Open, model-neutral software worker with sandbox execution | Adopt as a Worker adapter, not as the control plane. |

### 5.2 The evidence against default multi-agent organizations

The empirical literature does not support adding agents merely to mirror a human org chart:

- [Why Do Multi-Agent LLM Systems Fail?](https://arxiv.org/abs/2503.13657) analyzed multiple frameworks and more than 150 tasks, finding 14 failure modes across specification/design, inter-agent misalignment, and verification/termination. Gains over single-agent systems were often minimal.
- [Should we be going MAD?](https://openreview.net/forum?id=CrUmgUaAQp), an ICML 2024 study, found multi-agent debate did not reliably outperform self-consistency or ensembling and was sensitive to tuning.
- More-agent sampling and voting can improve some tasks, but that is inference-time ensembling—not evidence that a CEO/CFO/CTO conversation creates expertise.

Company Command should require one of three justifications before spawning another agent:

1. **Parallelism:** the tasks can run independently and wall-clock time matters.
2. **Boundary:** the worker needs a genuinely different tool, data, permission, or sandbox scope.
3. **Verification diversity:** an independently evaluated verifier reduces correlated error.

Each multi-agent design must beat a single-agent baseline on task success, cost, latency, and policy violations before it is promoted.

### 5.3 Protocols

- [MCP](https://modelcontextprotocol.io/specification/2025-11-25/basic) is the preferred interface for discoverable tools and context. Its HTTP authorization profile can use OAuth, scopes, audience binding, PKCE, and step-up flows. MCP does not provide business scheduling, safe tool semantics, or company authorization by itself.
- [A2A 1.0](https://github.com/a2aproject/A2A/blob/main/docs/specification.md) is useful for discovery and task exchange between independent, opaque agent systems. Use it at company or vendor boundaries. A typed internal job API is simpler within one Company Command deployment.
- OpenTelemetry GenAI conventions or [OpenInference](https://arize-ai.github.io/openinference/spec/) should describe model calls, agent steps, tools, retrieval, timing, and token cost. Company Command’s event ledger remains the authoritative audit trail; telemetry is an operational projection.

### 5.4 Open-model serving

Use a stable internal Model API and test compatibility rather than assuming every “OpenAI-compatible” endpoint behaves identically.

| Serving option | Recommended use |
|---|---|
| [vLLM](https://docs.vllm.ai/en/latest/) | Default production GPU server. Supports OpenAI-style APIs, tool calling, reasoning parsers, structured output, embeddings, and broad model coverage. |
| [SGLang](https://docs.sglang.io/docs/basic_usage/openai_api_completions) | Alternative for high throughput, advanced serving, LoRA, structured decoding, and distributed deployments. Its documented OpenAI surface is suitable for the native Model API; do not route Codex to it unless a supported release passes Company Command’s Responses conformance suite. |
| [llama.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md#post-v1responses-openai-compatible-responses-api) | Laptop, CPU, Apple Silicon, edge, and quantized deployments, including a documented Responses endpoint. Function calling quality still depends on the model and chat template. |
| [LiteLLM](https://docs.litellm.ai/) | Optional gateway for virtual keys, budgets, routing, fallbacks, and spend tracking. Pin, isolate, and minimize its credentials like any security-sensitive proxy. |

CompanySpec should refer to profiles such as <code>planner-high</code>, <code>extractor-fast</code>, and <code>code-worker</code>. Deployment configuration maps those profiles to model/provider/version triples. Promotion requires role-specific evaluation of tool-call accuracy, schema compliance, abstention, recovery, latency, and cost.

Publish a capability matrix for each model endpoint. The Codex adapter needs a tested subset of the Responses API rather than generic Chat Completions compatibility; all adapters need declared behavior for streaming, tool calls, structured output, cancellation, errors, and context limits. Conformance tests must reject an endpoint that advertises a feature but does not implement it reliably. Persist the resolved provider, model, tokenizer/chat template, serving version, capability snapshot, and configuration digest on every attempt so the execution context can be reconstructed and audited; stochastic or hosted output is not guaranteed to reproduce exactly.

## 6. Recommended Company Command architecture

~~~mermaid
flowchart TB
    Spec[Versioned CompanySpec and CompanyPack] --> Compiler[Manifest compiler and validator]
    Compiler --> Control[Company Command API and transaction boundary]
    Control <--> Workflow[DBOS durable execution]
    Control <--> UI[Operator UI: work, approvals, artifacts, audit, budgets]
    Control --> Business[(Business-state tables)]
    Control --> Events[(Audit-event tables in the same transaction)]
    Workflow --> Workers[Worker adapters]
    Workers --> Native[Bounded native agent]
    Workers --> Codex[Codex App Server]
    Workers --> OpenHands[OpenHands]
    Workers --> Deterministic[Deterministic domain services]
    Native --> Models[Model gateway]
    Codex --> Models
    OpenHands --> Models
    Models --> Open[vLLM / SGLang / llama.cpp]
    Models --> Hosted[Optional hosted providers]
    Workers --> Intent[Typed ActionIntent]
    Intent --> Policy[Default-deny policy and capability gateway]
    Policy --> Approval[WebAuthn approval service]
    Approval --> Policy
    Policy --> Executor[Effect executor, connectors, and reconciliation]
    Executor --> Control
    Events --> Memory[Derived search and memory indexes]
    Events --> OTel[OpenTelemetry / OpenInference]
~~~

The ownership boundary is deliberate. Company Command tables own company and business state, policy, budgets, artifacts, action revisions, approvals, and outcomes. DBOS owns scheduling, queues, checkpoints, timers, and execution history. A business-state transition and its audit event commit atomically in a DBOS-aware Postgres transaction; DBOS execution state must never be projected back over a newer Company Command business revision. Bind each workflow run to an implementation/build digest and use compatible upgrades or blue-green draining rather than silently changing code beneath a durable run.

### 6.1 CompanySpec and compiler

The CompanySpec is the portable definition of a company. The compiler validates references, denies ambiguous authority, materializes database records, and produces an immutable compiled revision.

A CompanyPack is also a supply-chain boundary. Keep declarative manifest data separate from executable worker images, connector code, and domain services. Admit executable components only by immutable digest after signature/provenance, license, compatibility, vulnerability, and sandbox-policy checks. Pack-supplied code never executes inside the trusted compiler, policy gateway, or control-plane process.

It defines:

- mission, goals, KPIs, and owners;
- roles as contracts;
- skills and deterministic domain functions;
- tool and data grants;
- model profiles and budgets;
- workflows and typed handoffs;
- risk and approval policy;
- memory namespaces and retention;
- evaluation suites;
- CompanyPack assets and templates.

The compiler must reject:

- an unknown role, tool, workflow, or schema;
- a role with write authority but no explicit action policy;
- cycles without an explicit loop bound;
- a workflow side effect without declared idempotency or reconciliation semantics;
- a high-risk action without an eligible approver;
- incompatible pack or schema versions;
- a default-allow capability.

### 6.2 Core records

The minimum durable schema includes:

- **Company** and immutable CompanyRevision;
- **Principal** for human, agent, service, and external organization identities;
- **IdentitySource**, RoleDefinition, and RoleAssignment with authoritative membership provenance, validity, and lifecycle status;
- **Goal**, WorkflowDefinition, Task, TaskRun, and StepRun;
- **Attempt** and WorkerLease with lease epoch, fencing token, heartbeat, and cancellation state;
- **Artifact** with schema, content hash, provenance, sensitivity, and retention;
- **ActionIntent** with immutable revision, canonical arguments, connector and canonicalizer versions, and external preconditions; risk is derived server-side from the trusted action definition and arguments, never accepted from the worker;
- **PolicyDecision**, ApprovalRequest, and ApprovalAssertion;
- **CapabilityGrant** with scope, expiry, delegation chain, and revocation;
- **BudgetAccount** and atomic BudgetReservation with currency, integer minor units, period, and release/settlement state;
- **ExternalOperation**, ExecutionReceipt, and append-only Event, including provider operation identifiers and reconciliation state;
- **ModelInvocation**, ToolInvocation, cost, and evaluation result.

Budget checks reserve integer minor units atomically against a currency, accounting period, and timezone before concurrent work or an external action begins. Completion settles the reservation; denial, cancellation, or a known non-effect releases it; an unknown external outcome holds it until reconciliation. Never compare unqualified floating-point money values.

### 6.3 Task state machine

A useful initial state machine is:

<code>DRAFT → READY → RUNNING → WAITING_FOR_HUMAN → COMMITTING → SUCCEEDED</code>

with explicit transitions to <code>FAILED_RETRYABLE</code>, <code>FAILED_FINAL</code>, <code>COMPENSATING</code>, and <code>CANCELLED</code>.

External effects add <code>OUTCOME_UNKNOWN</code> and <code>RECONCILING</code>. A provider can commit an operation and time out before Company Command receives the receipt, so arbitrary effects cannot honestly be described as exactly-once. Use a stable idempotency key where the provider supports one, record provider operation IDs, prefer version/ETag/nonce conditional writes, and reconcile with a read after an ambiguous timeout. A consequential action with an unknown outcome is never retried blindly; it remains blocked for automated reconciliation or explicit manual resolution.

The worker may create artifacts and action intents while running. It cannot transition its own consequential action to committed. Only the gateway, after current policy evaluation and any required approval, can create an execution receipt.

### 6.4 Worker contract

Every worker implements the same narrow lifecycle, with capabilities such as checkpoint, session resume, steering, and hard cancellation negotiated per adapter:

1. accept a signed task envelope, attempt ID, current worker lease, and scoped capability token;
2. report heartbeats and structured progress;
3. read allowed artifacts and data;
4. emit typed artifacts, questions, or action intents;
5. checkpoint or stop at a durable boundary;
6. accept supported steer, cancel, resume, or expiry operations; otherwise stop and restart at the last artifact/task boundary;
7. return usage and provenance.

Every worker mutation carries the attempt ID, lease epoch/fencing token, monotonically ordered command sequence, and an idempotent result ID. The gateway rejects a stale or superseded worker, even if it continues after a timeout. Cancellation revokes the capability immediately and terminates the runtime where the adapter supports it.

Workers do not write arbitrary control-plane rows. They use a company API that derives tenant context and enforces task, role, lease, and state boundaries. Worker runtimes start with environment credentials stripped and deny-by-default egress; an Company Command credential broker permits only the control API, model proxy, artifact service, and explicitly approved read endpoints. MCP servers, apps, and external tools are exposed through Company Command’s policy gateway rather than configured directly into workers.

The Codex adapter uses a pinned machine-level hardened profile: worker-local provider or sandbox overrides are rejected, direct apps and MCP are disabled, and shell/network capabilities are limited by the task sandbox and Company Command gateway. An opaque Codex or OpenHands session reference is an optimization, not portable durable state.

### 6.5 Example CompanySpec

This is illustrative; the first implementation should publish a JSON Schema and compiler tests before treating the format as stable.

~~~yaml
apiVersion: comcmd.dev/v1alpha1
kind: Company
metadata:
  name: example-studio
  revision: 1

mission:
  statement: Ship small, tested products with bounded financial risk.
  owner: human:board
  kpis:
    - id: validated_products
      target: 2
      period: quarter

identitySources:
  - id: workforce-directory
    protocol: oidc-scim
    authoritativeFor: [human:board, human:finance]
    lifecycle: joiner_mover_leaver

modelProfiles:
  planner-high:
    capability: reasoning_and_tools
    billingCurrency: USD
    maxCostPerTaskMinorUnits: 800
    fallback: defer
  extractor-fast:
    capability: structured_extraction
    billingCurrency: USD
    maxCostPerTaskMinorUnits: 30
    fallback: retry_then_defer
  code-worker:
    capability: repository_engineering
    workerPreference: [codex, openhands]

roles:
  - id: product-lead
    purpose: Convert evidence into a scoped product proposal.
    skills: [market-synthesis, product-brief]
    modelProfile: planner-high
    tools:
      allow: [research.search, artifacts.write]
    dataScopes: [market.public, company.product]
    mayDelegateTo: [researcher]
    budget:
      currency: USD
      period: month
      timezone: UTC
      limitMinorUnits: 15000
    escalation:
      uncertaintyAbove: 0.25
      to: human:board

  - id: researcher
    purpose: Gather cited evidence and identify uncertainty.
    skills: [web-research, source-verification]
    modelProfile: extractor-fast
    tools:
      allow: [research.search, research.fetch, artifacts.write]
    dataScopes: [market.public]

  - id: human:board
    principalKind: human
    purpose: Own mission and approve consequential product commitments.
    approvalScopes: [product-commitment, external-publishing, finance]
    membership:
      source: workforce-directory
      group: board-approvers
      revalidateAtApproval: true

  - id: human:finance
    principalKind: human
    purpose: Independently control financial commitments.
    approvalScopes: [finance]
    membership:
      source: workforce-directory
      group: finance-approvers
      revalidateAtApproval: true

workflows:
  - id: validate-product
    version: 1
    inputSchema: schemas/product-hypothesis.json
    steps:
      - id: research
        runAs: researcher
        outputSchema: schemas/evidence-pack.json
      - id: brief
        runAs: product-lead
        needs: [research]
        outputSchema: schemas/product-brief.json
      - id: approve
        type: humanGate
        needs: [brief]
        policy: product-commitment
    exitCriteria:
      evaluator: evals/product-brief.yaml
      minimumScore: 0.85

actions:
  - id: publish-external-copy
    tool: publishing.publish
    connectorVersion: publishing-v2
    canonicalizerVersion: comcmd-action-v1
    riskPolicy:
      defaultTier: R2
      rules:
        - when:
            environment: production
          tier: R3
    proposers:
      - role: product-lead
        workflow: validate-product
        steps: [brief]
    argumentConstraints:
      destination: [company-site]
      environment: [staging, production]
    effectPolicy:
      idempotency: provider_key
      unknownOutcome: reconcile
      requiredPreconditions: [targetRevision]
    approval:
      authenticatorPolicy: high-assurance-hardware
      requirements:
        - role: human:board
          count: 1
      distinctPrincipals: true
      excludeRequester: true
      ttl: 10m
  - id: spend-money
    tool: finance.pay
    connectorVersion: finance-v1
    canonicalizerVersion: comcmd-action-v1
    riskPolicy:
      defaultTier: R3
    proposers:
      - role: product-lead
        workflow: validate-product
        steps: [brief]
    argumentConstraints:
      currency: [USD]
      maxAmountMinorUnits: 25000
      sourceAccount: [operations-primary]
      destinationClass: [approved-vendor]
    effectPolicy:
      idempotency: provider_key
      unknownOutcome: reconcile
      requiredPreconditions: [accountVersion, budgetReservation]
    approval:
      authenticatorPolicy: high-assurance-hardware
      requirements:
        - role: human:board
          count: 1
        - role: human:finance
          count: 1
      distinctPrincipals: true
      excludeRequester: true
      ttl: 5m

memory:
  canonical: postgres
  namespaces:
    - id: market-evidence
      sources: [artifacts:evidence-pack]
      retrieval: full_text
      retention: 180d
      requireProvenance: true

evaluations:
  required:
    - workflow-contracts
    - policy-negative-cases
    - tool-schema-compliance
    - retrieval-provenance
~~~

The trusted <code>riskPolicy</code> maps an action category and canonical arguments to an <code>R0–R4</code> tier; the gateway evaluates it and the worker never supplies the result. A missing mapping is a rejection. The compiler must also reject an authenticator policy, connector guarantee, or reconciliation mode that the deployment cannot enforce. The payment example therefore becomes deployable only when the high-assurance and quorum features are enabled; it must never silently degrade to a weaker approval.

## 7. Human-in-the-loop and passkey strategy

### 7.1 Separate credential authentication from action authorization

A passkey authenticates control of a credential bound to an Company Command account. It does not by itself prove legal identity, current employment or role, understanding, or authority for the action. Company Command must establish those through identity proofing and provisioning provenance, authoritative role assignment, joiner-mover-leaver controls, and current policy evaluation.

For each gated action:

1. The worker submits a typed ActionIntent; the gateway resolves the trusted action definition and derives risk from its canonical arguments.
2. The server creates an immutable action revision and domain-separated digest over the canonicalization schema/version, connector version, resolved tenant/account/target, provider defaults, significant arguments, artifact hashes, and target-side preconditions.
3. Policy determines required authenticator policy, approver roles and counts, separation of duty, budget reservation, and expiry.
4. For every approval attempt, the server creates an unpredictable challenge of at least 16 bytes, valid briefly and usable once, bound to exactly one action revision and digest, the <code>action-approval</code> purpose, approver principal or approval slot, authenticated session, policy version, and expiry. Quorum members receive separate challenges over the same revision.
5. A minimal approval UI renders significant fields from server-owned structured data, not model-authored prose.
6. The authenticator returns a WebAuthn assertion with user verification required.
7. A maintained conforming library performs the complete [WebAuthn assertion verification procedure](https://www.w3.org/TR/webauthn-3/#sctn-verifying-assertion): bind credential ID and user handle to the approver; verify <code>clientData.type</code>, exact challenge, allowed origin and RP ID hash, user presence and trusted user verification, stored UV initialization state, backup eligibility/state policy, signature/public key/algorithm, and counter risk; and enforce the deployment’s cross-origin/top-origin policy where applicable. Separately, Company Command verifies that the server-side challenge and approval request are unexpired and purpose/session bound, the registered credential remains allowed under current metadata/revocation policy, the approver remains eligible, and the attempt is not a replay. Challenge consumption and approval creation are atomic.
8. For a quorum, Company Command verifies distinct human principal IDs, explicit per-role counts, requester exclusion, identical unmodified action revision, unexpired server-side approval/challenge records, current roles, and any independent-device/custody rule. Completing a threshold is atomic; changing action or policy invalidates all prior approvals.
9. Immediately before execution, the gateway revalidates policy, roles, budget reservation, capability, digest, expiry, and external preconditions. It uses the target’s atomic transaction, conditional write, version/ETag, nonce, or equivalent facility where available.
10. The executor uses a stable idempotency key where supported, records provider operation identifiers and receipts, and enters reconciliation rather than blindly retrying an ambiguous result.

Plain WebAuthn signs contextual authentication data containing a challenge and origin; it has no trusted standardized display for arbitrary Company Command fields. The preview is therefore a defense-in-depth acknowledgment UI, not cryptographic evidence of what the approver saw or understood. Host high-risk approval on an isolated origin with an exact origin allowlist, no untrusted or third-party scripts, strict CSP and Trusted Types, CSRF protection, and framing disabled. The [OWASP Transaction Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html) recommends displaying significant data and enforcing it server-side. For applicable web payments, evaluate [Secure Payment Confirmation](https://www.w3.org/TR/secure-payment-confirmation/) or another trusted-display mechanism.

### 7.2 Business-risk tiers

These <code>R0–R4</code> business-risk tiers are not NIST Authentication Assurance Levels.

| Tier | Examples | Default policy |
|---|---|---|
| R0: observe | Read public data, inspect artifacts, sandboxed analysis | Automatic and logged |
| R1: bounded internal | Reversible draft edits inside a versioned workspace | Automatic with scope, budget, and rollback |
| R2: limited external | Create a draft ticket, stage unpublished content, update an explicitly non-production record | Exact preview, one verified passkey where AAL2-style risk is acceptable, short TTL, and target precondition |
| R3: consequential | Publish or send as a human, deploy production, access secrets, sign/submit, pay, or delete durable data | Fresh high-assurance authenticator under an approved policy, exact preview, conditional commit, and distinct-person quorum when consequences justify it |
| R4: invariant-prohibited | Unbounded fund movement, self-granting authority, disabling audit, or retroactively approving a pending action | Deny as a non-bypassable invariant |

Emergency access must be narrowly pre-authorized, time-bounded, controlled by distinct humans, independently logged and notified, and mandatorily reviewed. It may not self-grant authority, disable audit, or bypass an R4 invariant. Ordinary policy changes use a separately governed administrative workflow, not break-glass.

NIST [SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b/aal/) says AAL3 requires two factors, replay resistance, protected channels, authentication intent, phishing-resistant public-key authentication, a non-exportable hardware-protected private key, and applicable cryptographic validation. Authentication intent proves an explicit authentication response, not understanding of the business action. Synced passkeys are excluded from AAL3; device-bound, <code>BE=0</code>, “hardware-backed,” and attested are each insufficient alone. Any AAL3 claim must verify the complete authenticator, activation, key-protection, protocol, verifier, reauthentication, and validation requirements.

Synced passkeys may be accepted only for tiers whose risk analysis permits AAL2-style authentication and whose user-verification and sync-fabric policy requirements are met. They are not accepted where non-exportability or independent custody is required.

### 7.3 PIN, biometric, enrollment, and recovery

- In a standard WebAuthn ceremony, biometric data is handled locally by the authenticator and is not sent to the relying party; platform software and a separate biometric-proofing flow have their own privacy boundaries.
- A UV-capable passkey can act as a multi-factor cryptographic authenticator only when Company Command requests and verifies UV and established trust in that credential’s UV correctly. UV says some authenticator-local verification occurred; it does not reveal whether PIN, biometric, or multiple methods were used, or identify a natural person.
- A local authenticator PIN is an activation secret and stays within the authenticator. A biometric and that PIN are normally alternative activation methods, and a non-biometric alternative must remain available.
- A server-verified Company Command PIN can add a knowledge factor, but is phishable and does not improve WebAuthn’s verifier-impersonation resistance or prove a second device or person.

For the highest tier, require <code>BE=0</code> plus verified attestation to an allowed authenticator model, acceptable key-protection and UV properties, current metadata/security status, and any required certification. Persist registration evidence and continuously evaluate revocation, compromised-attestation, UV-bypass, and firmware/security updates. Attestation is evidence to evaluate, not a magic trust bit.

An independently stored, tested, pre-enrolled second hardware key at equivalent assurance is an alternate authenticator that may avoid recovery; it is not itself account recovery. Quorum means distinct human principals—not merely distinct credentials—and the most critical actions should also require independent device custody.

New authenticator binding requires [step-up authentication](https://pages.nist.gov/800-63-4/sp800-63b.html#binding-an-additional-authenticator) at the lower of the account’s maximum available AAL and the new authenticator’s intended AAL, plus full registration verification, credential/account binding, independent notification, and supervised or separately approved enrollment for the highest tier. Recovery follows a documented risk-assessed method, not liveness alone. On binding, recovery, suspected compromise, or role change, notify independently; revoke or suspend affected credentials, sessions, capabilities, challenges, and pending approvals; revalidate organizational roles; and impose a risk-based cooling-off period before high-tier approval.

An iProov-style liveness/PAD provider may be one component of documented remote identity proofing or exceptional recovery. It is neither sufficient identity proofing nor action authorization by itself and must be combined with evidence validation, identity verification, injection/forged-media controls, protected capture, consent, retention limits, and recovery notifications. It is not required in the routine approval path.

## 8. Memory and RAG

RAG is not company memory. It is one derived way to find source material.

Use four stores:

1. **Transactional truth:** normalized Postgres records for goals, decisions, tasks, approvals, policies, budgets, and outcomes.
2. **Immutable evidence:** versioned artifacts and append-only events with hashes and provenance.
3. **Document retrieval:** permission-filtered full-text search over approved sources, with vector retrieval only where evaluation demonstrates benefit.
4. **Derived agent memory:** optional summaries, episodes, and temporal facts with confidence, validity windows, expiry, and source links.

Never let an LLM-written memory silently become a company fact. A derived memory may help a worker, but authoritative decisions resolve back to canonical records and source artifacts.

[LongMemEval](https://arxiv.org/abs/2410.10813) reports roughly a 30% accuracy drop across sustained interactions and evaluates extraction, multi-session reasoning, time, updates, and abstention. [LongMemEval-V2](https://arxiv.org/abs/2605.12493) extends the problem to agent experience, workflow knowledge, environment changes, and recurring failure modes. These results argue for explicit retrieval evaluations rather than faith in a long context window.

Start with Postgres full-text search and source-level access control. Add pgvector and a reranker only if they improve measured recall for a CompanyPack. Consider [Graphiti](https://github.com/getzep/graphiti) only when changing relationships and point-in-time questions are central; it adds useful temporal provenance but also operational and extraction complexity. Treat vendor-authored memory benchmark results as hypotheses to reproduce.

Every memory entry should carry:

- source artifact/event IDs;
- writer principal and task;
- extraction method and model version;
- created, valid-from, valid-until, and superseded timestamps;
- confidence and sensitivity;
- tenant and namespace;
- deletion/retention policy.

## 9. Security model

The model is an untrusted planner operating inside a constrained environment. Model alignment and prompt-injection classifiers are defense-in-depth, not authority controls.

| Threat | Required control |
|---|---|
| Prompt injection from web, email, files, or tools | Treat external content as typed untrusted data; separate it from control instructions; carry taint/provenance; authorize each tool and destination deterministically; encode outputs; restrict tools and egress; use scanners only as defense-in-depth |
| Confused deputy / stolen worker token | Workload-authenticated, sender-constrained capabilities scoped to tenant, audience, resource, action, arguments, attempt, and short TTL; every tool verifies them; delegation may only narrow scope and lifetime |
| Agent-to-host escape | Per-run unprivileged container/VM; syscall, device, filesystem, and deny-default network policy; no host or Docker socket; immutable patched runtime; escape detection and forced termination |
| Stale approval / TOCTOU / ambiguous effect | Immutable action revision, short TTL, single-use challenge, target-side atomic precondition or conditional write, provider idempotency/operation ID, and <code>OUTCOME_UNKNOWN</code> reconciliation |
| Cross-tenant access | Server-derived tenant on records, queues, caches, search/vector indexes, artifacts, logs/traces, credentials, and model routing; row/path checks and negative authorization tests |
| Memory poisoning | Signed or authorized ingestion, provenance and trust labels, permission-filtered retrieval, derived-memory quarantine, expiry and supersession, and explicit promotion before derived memory becomes authoritative |
| Supply-chain compromise | Immutable digests, verified signatures/provenance, SBOMs, vulnerability/revocation monitoring, separate signing keys, compatibility tests, and sandboxing for worker images, connectors, MCP servers, skills, and models |
| Budget or resource runaway | Atomic reservations plus per-task, role, company, model, tool, concurrency, wall-clock, retry, output, and network quotas; circuit breakers outside the model |
| Approval fatigue / deceptive UI | Deduplication, rate limits, isolated approval origin, significant-field preview, no LLM-authored confirmation UI, and no batching unless every item is one displayed canonical bundle covered by one digest |
| Session, enrollment, or recovery takeover | Short sessions, purpose-separated challenges, rigorous authenticator binding, independent notification, recovery controls, cooling-off, role revalidation, and revocation of pending approvals |
| Spoofed or rogue agents and cascading failure | Authenticated workload identity, signed task envelopes, fencing, bounded delegation, circuit breakers, independent verification for critical claims, and containment at company boundaries |
| Audit tampering or truncation | Restricted append-only writers, signed/hash-linked exported receipts, independently retained signed checkpoints or WORM storage, key separation, retention enforcement, and restore/verification tests |

Paperclip’s patched 2026 vulnerabilities are especially instructive: agent-editable adapter configuration crossed into host shell execution, while a separate open-signup, self-approved CLI, and import-authorization chain enabled unauthenticated RCE. Company Command must keep role content, worker configuration, host launch configuration, enrollment, and business authorization in separate trust domains.

Agent identity standards are still emerging. NIST’s February 2026 [agent identity and authorization concept paper](https://www.nist.gov/news-events/news/2026/02/new-concept-paper-identity-and-authority-software-agents) is a draft, non-normative scoping and request-for-input document for a possible implementation project. Its useful areas of interest are distinguishing human and non-human identities, representing delegated/on-behalf-of authority, binding humans to high-risk loops, and preserving verifiable logs.

## 10. Evaluation and operational evidence

Company Command should promote a CompanyPack only when it passes deterministic tests and scenario evaluations.

### Required test layers

1. **Compiler tests:** schema versions, references, cycles, money semantics, budgets, grants, proposer constraints, approvers, executable-pack admission, and default-deny behavior.
2. **Workflow tests:** retries, crash recovery, timers, cancellation, compensation, duplicate delivery, zombie-worker fencing, human waits, unknown outcomes, reconciliation, and code-version upgrades/draining.
3. **Policy negative tests:** unknown action, widened arguments, expired approval, replay, changed artifact, wrong tenant, wrong approver, self-approval, stale capability, target-precondition change, and budget races.
4. **WebAuthn and quorum tests:** invalid signature/key/algorithm/type/challenge/origin/top-origin/RP ID; missing UP/UV or untrusted UV initialization; backup-policy, credential binding, metadata, counter, cross-purpose, cross-session, replay, enrollment, recovery, and notification failures; same-person quorum, overlapping roles, action mutation, and expiry before execution.
5. **Tool contract tests:** malformed model output, schema edge cases, idempotency, rate limits, partial failure, timeout-after-commit, conditional-write failure, read-after-write verification, and manual reconciliation.
6. **Worker and model-endpoint conformance:** task/lease/artifact contracts across native, Codex, and OpenHands; Responses capability, streaming, tool-call, schema, cancellation, error, and context-limit behavior for each routed model server.
7. **Model evaluations:** task success, tool choice, argument accuracy, abstention, recovery, cost, latency, and policy compliance by profile.
8. **Retrieval evaluations:** source recall, temporal correctness, permission filtering, citation precision, and abstention.
9. **Adversarial tests:** prompt injection, poisoned memory, malicious MCP output, credential requests, cross-agent trust escalation, XSS, clickjacking, deceptive previews, registration substitution, and bundled-action mutation.

### Product metrics

- end-to-end workflow success;
- verified side-effect correctness;
- human intervention rate and approval latency;
- retry and recovery success;
- policy-denial correctness and policy escapes, with a target of zero escapes;
- cost per successful outcome;
- artifact acceptance and rework rate;
- retrieval citation accuracy;
- rollback or compensation success;
- percentage of actions with complete provenance;
- single-agent versus multi-agent delta.

Do not optimize “number of agents,” “messages exchanged,” or “hours worked.” Those are theater metrics.

## 11. Implementation roadmap

### Phase 0 — contracts and a walking skeleton

Deliver:

- CompanySpec JSON Schema and compiler;
- Postgres core records, atomic business-state/event transitions, and the explicit Company Command/DBOS ownership boundary;
- DBOS workflow execution, queueing, human waits, and recovery from the first executable slice;
- one deterministic workflow with a native worker, attempt leases, and fencing;
- a minimal typed ActionIntent, pure default-deny capability registry, local conditional effect adapter, and explicit reconciliation state;
- one thin AutoSteam vertical slice that produces a typed artifact and performs one controlled, reversible local-state mutation through the gateway;
- model profile abstraction with one local OpenAI-compatible backend;
- CLI that instantiates a company revision and runs the thin slice;
- workflow build digests and a compatible-upgrade/blue-green-drain procedure;
- compiler, crash, recovery, duplicate-delivery, unknown-outcome, and fencing tests.

Exit gate: a process can crash at every step and resume without duplicating the local effect; any deliberately injected ambiguous result becomes an explicit reconciled or manually resolvable state rather than a blind retry.

### Phase 1 — governed effects and human approval

Deliver:

- production action definitions, external connector registry, and scoped capability issuance on top of the Phase 0 gateway;
- canonical action digest, conditional effect execution, and reconciliation;
- atomic BudgetReservation and hard per-task/model/tool/company limits before external writes;
- authoritative human provisioning and joiner-mover-leaver integration with role revalidation at approval and commit;
- WebAuthn enrollment, full assertion verification, high-assurance authenticator policy, and distinct-principal quorum;
- operator inbox for tasks, approvals, artifacts, and receipts;
- deny-default worker egress, stripped environment credentials, task-scoped capabilities, credential broker, and sandbox profiles;
- connector secret rotation and revocation;
- workflow dead-letter/manual recovery, backup/restore tests, compatible schema migrations, and minimal metrics/tracing;
- policy, replay, quorum, approval-origin, and ambiguous-effect test suites.

Exit gate: no worker can perform an external write except through the gateway; every write is budgeted and bound to an immutable action revision; every outcome is known or explicitly reconciling, never silently retried.

### Phase 2 — first CompanyPack and worker portability

Deliver:

- the complete AutoSteam vertical as the first CompanyPack while keeping pure deterministic functions in-process;
- hardened Codex App Server and OpenHands adapters with worker/model conformance suites;
- artifact store and permission-filtered Postgres full-text retrieval, adding vectors only if pack evaluation demonstrates benefit;
- richer budget accounting and forecasting on top of Phase 1 reservations;
- richer OpenTelemetry/OpenInference traces;
- pack-level evaluations and local/open-model baseline.

Exit gate: the same typed workflow can run with at least two worker adapters and produces equivalent contract-valid artifacts.

### Phase 3 — measured multi-agent operation

Deliver only where evaluation justifies it:

- parallel subtask fan-out and typed aggregation;
- independent verifier workers;
- delegation-chain capabilities;
- optional A2A gateway for external systems;
- vector or temporal/graph memory only for demonstrated use cases;
- a Temporal migration ADR only if measured HA, scale, service-isolation, SDK-gap, or operational requirements exceed the DBOS design; any adoption drains DBOS histories and starts new runs from Company Command business state.

Exit gate: the multi-agent variant materially beats the single-agent baseline without unacceptable cost, latency, or policy regressions.

### What not to build in the first version

- a simulated office chat;
- self-modifying roles or policies;
- arbitrary nested agent spawning;
- a custom vector database;
- blockchain or public ledger anchoring;
- universal A2A inside one deployment;
- model-per-role fine-tunes;
- iProov on every approval;
- multi-cloud KMS agility;
- automated legal, financial, or production authority without explicit policy and human gates.

## 12. Build, adopt, and defer decisions

| Capability | Decision |
|---|---|
| Company manifest and compiler | Build in Company Command |
| Durable MVP workflow | Adopt DBOS |
| Alternative workflow engine | Keep Temporal as a candidate for explicit measured gaps; migration requires draining histories |
| Generic multi-agent framework | Do not adopt as core |
| Coding worker | Adapt Codex and OpenHands |
| Non-coding worker | Build a small bounded native runner |
| Model serving | Adopt vLLM/SGLang/llama.cpp behind one internal API; route Codex only to a Responses-conformant endpoint |
| Model gateway | Start small; optionally adopt LiteLLM after security review |
| Tools | MCP at integration edges, wrapped by Company Command policy |
| External agents | A2A only at independent-system boundaries |
| Canonical data | Postgres |
| Vector/graph memory | Derived and optional |
| Policy gate | Build a small Mandamus-inspired pure module inside the trusted gateway |
| Human approval | Build WebAuthn-authenticated action approval |
| Liveness | Optional enrollment/recovery adapter only |
| Audit | Append-only events first; signed/exportable receipts where needed |
| UI | Work/approval/artifact/audit inbox first; chat later |
| Paperclip | Benchmark and limited spike; do not adopt as initial trust base |

## 13. Decision log

1. Company Command is a company control plane and pack format, not an artificial org-chat simulator.
2. Work and artifacts are first-class; sessions are replaceable execution details.
3. DBOS/Postgres is the first durable runtime; Temporal remains a candidate only for measured gaps and is not a drop-in backend switch.
4. Roles compose skills, tools, scopes, budgets, and evaluations.
5. Open and hosted models share one profile-based boundary.
6. Codex and OpenHands are worker adapters.
7. Mandamus is reduced to authority primitives.
8. AutoSteam becomes the first CompanyPack.
9. WebAuthn passkeys replace routine liveness approval.
10. Synced passkeys are not treated as AAL3.
11. The highest tier uses hardware-bound credentials and dual control where justified.
12. Every effect is authorized at commit time and evidenced; connectors declare idempotency and reconciliation semantics, and ambiguous outcomes are never blindly retried.
13. RAG and agent memory are derived indexes, never company truth.
14. Multi-agent designs must beat a single-agent baseline.

## 14. Immediate next actions

1. Write ADR-001 for DBOS-first durability, state ownership, recovery/HA, workflow-code upgrades, and measured Temporal graduation criteria.
2. Define CompanySpec v1alpha1 as JSON Schema with example packs.
3. Define the Worker, ActionIntent, Approval, Artifact, and Event contracts.
4. Review Mandamus licensing and provenance, then port permitted policy cases or create clean-room language-neutral test vectors before implementation.
5. Build a WebAuthn proof of concept with action revision, replay, expiry, and quorum tests.
6. Convert one AutoSteam workflow into a CompanyPack without changing its deterministic domain kernel.
7. Define the Model API capability matrix and conformance suite, then benchmark one local model on structured tool use through native, hardened Codex, and OpenHands workers.
8. Run a short Paperclip architecture spike against the current patched release, comparing recovery semantics, adapter/configuration trust, deployment defaults, authorization, license, data migration, schemas, and operator UX.
9. Add an evaluation gate before enabling any parallel-agent workflow.

## Primary source map

### Product architecture

- [Claude Cowork getting started](https://support.claude.com/en/articles/13345190-get-started-with-claude-cowork)
- [Claude Cowork architecture](https://support.claude.com/en/articles/14479288-claude-cowork-architecture-overview)
- [Anthropic containment engineering](https://www.anthropic.com/engineering/how-we-contain-claude)
- [Anthropic knowledge-work plugins](https://github.com/anthropics/knowledge-work-plugins)
- [ChatGPT Work and Codex usage map](https://learn.chatgpt.com/docs/use-chatgpt#choose-how-you-want-to-work)
- [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference#configtoml)
- [Codex App Server API](https://learn.chatgpt.com/docs/app-server#api-overview)
- [OpenAI Symphony](https://openai.com/index/open-source-codex-orchestration-symphony/)

### Open orchestration and infrastructure

- [DBOS documentation](https://docs.dbos.dev/)
- [DBOS architecture and guarantees](https://docs.dbos.dev/architecture)
- [DBOS workflow recovery](https://docs.dbos.dev/production/workflow-recovery)
- [DBOS workflow upgrades](https://docs.dbos.dev/python/tutorials/upgrading-workflows)
- [Temporal documentation](https://docs.temporal.io/)
- [LangGraph interrupts](https://langchain-ai.github.io/langgraph/concepts/breakpoints/)
- [AutoGen human-in-the-loop](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/human-in-the-loop.html)
- [OpenHands runtime architecture](https://docs.openhands.dev/openhands/usage/architecture/runtime)
- [Paperclip product definition](https://github.com/paperclipai/paperclip/blob/master/doc/PRODUCT.md)
- [MCP specification](https://modelcontextprotocol.io/specification/2025-11-25/basic)
- [A2A specification](https://github.com/a2aproject/A2A/blob/main/docs/specification.md)

### Evidence and security

- [Why Do Multi-Agent LLM Systems Fail?](https://arxiv.org/abs/2503.13657)
- [Should we be going MAD?](https://openreview.net/forum?id=CrUmgUaAQp)
- [LongMemEval](https://arxiv.org/abs/2410.10813)
- [LongMemEval-V2](https://arxiv.org/abs/2605.12493)
- [NIST SP 800-63B-4 AAL requirements](https://pages.nist.gov/800-63-4/sp800-63b/aal/)
- [W3C WebAuthn Level 3 Candidate Recommendation Snapshot](https://www.w3.org/TR/webauthn-3/)
- [W3C WebAuthn Level 2 Recommendation](https://www.w3.org/TR/webauthn-2/)
- [W3C Secure Payment Confirmation](https://www.w3.org/TR/secure-payment-confirmation/)
- [FIDO Metadata Service](https://fidoalliance.org/specs/mds/fido-metadata-service-v3.1-ps-20250521.html)
- [NIST SP 800-63B-4 account recovery](https://pages.nist.gov/800-63-4/sp800-63b.html#account-recovery)
- [NIST SP 800-63A-4 remote proofing controls](https://pages.nist.gov/800-63-4/sp800-63a/ial-general/)
- [OWASP transaction authorization](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html)
- [NIST software and AI agent identity project](https://www.nccoe.nist.gov/projects/software-and-ai-agent-identity-and-authorization)
