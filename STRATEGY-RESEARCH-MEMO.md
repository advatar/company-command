# Research Memo: Cowork, Harnesses, and the Mandamus/AutoSteam Extraction

**Status:** Research companion to `STRATEGY.md` (which is canonical) · 2026-07-15
**Author:** Johan + Claude (Opus 4.8)
**Scope:** How to turn the one-off patterns in `MandamusCo` and `autonomous-steam-studio` into a reusable framework, with the evidence behind those choices (Cowork teardown, harness landscape, passkey assurance, code-level inventory of both repos).

> **Read `STRATEGY.md` first — it is the decided plan; this file is the supporting research.** Where the two differ, `STRATEGY.md` wins. Two reconciliations were applied to this memo after comparing them:
>
> 1. **Passkey assurance (see §6).** An earlier draft of this memo treated "passkey + PIN" as an additive two-factor sufficient at the very highest tier and proposed *editing MandamusCo's `gate.mjs`* to collapse its top tier. Both points are corrected. Per WebAuthn/NIST SP 800-63B-4: a device PIN and a biometric are **alternative** local activation factors, not two independent factors; **synced passkeys are explicitly not AAL3** (their keys are exportable). So passkeys correctly replace iProov for *routine and most* approvals, but the **truly consequential tier uses a device-bound hardware authenticator plus distinct-person dual control**, not "passkey + app PIN." iProov drops to an *optional enrollment/recovery* adapter, never the per-transaction gate.
> 2. **Mandamus is extracted, not forked or modified (see §2, §6.4).** We do **not** change MandamusCo and do **not** take a runtime dependency on its JS control-plane. Acme is Python/DBOS/Postgres; we **reimplement a small "Mandamus-Lite"** — its canonical action intents, default-deny gate, approval state machine, scoped capabilities, and receipts — porting its test cases as language-neutral vectors, after a license check. The concepts are the asset; the code stays where it is.

---

## 1. Executive summary — the recommendation

**Build a thin framework, not a platform.** The state of the art (including Claude Cowork and OpenAI Codex) shows that a "company of agents" is not fine-tuned models per role — it is **one capable base model, differentiated per role by prompt + tools + scoped permissions**, driven by a supervisor loop, with a **human approval gate at the few irreversible actions**. Everything expensive is optional.

Concretely, the recommended stack — and the key correction after reading both codebases: **you already own the two halves of this framework.** AutoSteam is the company/orchestration half; MandamusCo's `control-plane/` is a far stronger governance/approval half than "a small passkey service." The framework is mostly *fusing* them, not building new.

| Layer | Recommendation | Why |
|---|---|---|
| **Model** | Open-weight (e.g. a strong open model behind an OpenAI-compatible gateway), Claude/GPT/Gemini as premium fallback | No per-role fine-tuning needed; role = prompt + tools. Mandamus's `agent-runtime.mjs` is *already* provider-agnostic (`gemini`/`claude`/`codex`/`simulated`) |
| **Harness (runtime)** | **OpenAI Codex** as the primary agent runtime, with **Claude Agent SDK** as a first-class alternative | Codex has native multi-agent orchestration + TOML role files; you already use it in AutoSteam, and Mandamus's doorkeeper already wires Codex/Claude Code over MCP |
| **Orchestration** | A **deterministic supervisor** (AutoSteam's `orchestrator.py` pattern) that calls role-agents in a declared order/graph; for cross-agent dependencies, adopt Mandamus's **A2A consult/precondition broker**; upgrade to a durable engine only when a company becomes long-running | Determinism + auditability beat "agents freelancing"; matches Cowork's parent/child model |
| **Company definition** | A single declarative **`company.yaml` + `roles/*.toml` + `skills/*.md`** manifest that the framework instantiates | This is the "instantiate any company" primitive; both repos already define roles as data |
| **Governance / approval** | **Reimplement Mandamus's authority primitives as a Python "Mandamus-Lite"** — tiered default-deny gate (adopt the T0→T3 model + the T1† bounded-auto idea), append-only signed receipts, sender-constrained scoped capabilities, canonical action intents. Port its tests as language-neutral vectors. **Do not fork, depend on, or modify MandamusCo's JS control-plane.** | The concepts (not the code) are the reusable asset; Acme's kernel is Python/DBOS/Postgres |
| **Human-in-the-loop auth** | **WebAuthn transaction authorization** — user-verified passkey bound one-to-one to an immutable action record, short TTL, commit-time revalidation. Passkeys replace iProov for routine/most approvals. **Highest tier = device-bound hardware authenticator + distinct-person dual control**, not "passkey + app PIN." iProov = optional enrollment/recovery adapter only. | Synced passkeys aren't AAL3 (NIST SP 800-63B-4); PIN and biometric are alternative activation factors, not additive |

**Answers to your direct questions, up front:**

- **Does Claude Cowork use fine-tuned per-role models?** No. It is a single base model (Sonnet-class) in a **parent/child agent architecture**: a persistent lead agent spawns isolated per-task child agents, each with its own context window, system prompt, tool set, and permissions. Roles are *context engineering*, not distinct weights — not "RAG," and no per-role fine-tuning. (Source: third-party teardown, Pluto Security.) **Both your repos already do it this way** (roles are system prompts + tool lists as data).
- **Is Codex a more suitable harness?** For an *open-model, multi-agent* framework, **yes, it's the strongest off-the-shelf starting point** — native subagent spawn/message/wait/terminate, TOML-declared roles, concurrency/nesting caps, per-agent sandboxes. AutoSteam already drives it; Mandamus's doorkeeper already bridges it to a gate over MCP. Claude Agent SDK is the close second (Anthropic-native).
- **Do we need Mandamus?** **We need its ideas, not the product — and we do not modify it.** Mandamus's control-plane is the genuinely valuable part (default-deny tiered gate, scoped capabilities, approval state machine, signed receipts, ~8.2k LOC, 289 tests). But Acme is Python/DBOS/Postgres and should not take a runtime dependency on a separate JS platform. So: **extract the authority primitives into a small Python "Mandamus-Lite," port the tests as vectors, leave MandamusCo untouched.** What's disposable is the six-agent roster and the iProov-parent framing.
- **iProov Liveness for approvals?** **Not needed as the default** — passkeys replace it for routine and most approvals. But the nuance matters: Mandamus reserves iProov for genuine-presence at its top tier. Rather than "passkey + PIN even at the top" (which is *not* a genuine two-factor upgrade — a device PIN and a biometric are alternative activation factors, and synced passkeys aren't AAL3), the highest-consequence tier should use a **device-bound hardware authenticator + distinct-person dual control**. iProov stays available only as an *optional identity-proofing adapter for enrollment/recovery*, never as the per-transaction authorization gate. (Details in §6.)

---

## 2. What you already have (and what to harvest from each)

You have already built the two halves of this framework independently. The job is to extract the generic spine from both.

### `autonomous-steam-studio` (AutoSteam) — the *orchestration + company* half

A polished **scaffold** for an autonomous Steam/iOS micro-game studio. The important architectural lessons:

- **Two notions of "agent," cleanly separated.** (a) Deterministic Python role-classes (`studio_core/agents/*.py`) implementing a simple `run(payload) -> AgentResult` protocol — these do the *mechanical* work and call **no LLM**. (b) The *intelligent* agents are the host coding assistants (Claude Code, Codex) driving that pipeline via **skills** (`skills/*/SKILL.md`) and **Codex role files** (`.codex/agents/autosteam-{market,qa,compliance,release}.toml`).
- **The role file is the reusable primitive.** Each `.codex/agents/*.toml` has `name`, `description`, `model_reasoning_effort`, and `developer_instructions`. This is exactly the "role = prompt + tools + permissions" abstraction Cowork and Codex both use.
- **Deterministic supervisor.** `studio_core/orchestrator.py` is a synchronous pipeline (market → director → publishing → qa → compliance) passing plain dicts. Its own docstring says "swap for Temporal/Prefect/Dagster when this becomes a long-running service." That is the right instinct.
- **Human-gated autonomy is already a first-class theme.** `config/studio.yaml: require_human_release_approval: true`; the `CompliancePacket` model hardcodes `human_approval_required = True`; MCP tools that execute code require an explicit `allow_game_execution: true` and are annotated `destructive`. The gates are enumerated, not incidental.
- **A genuinely reusable MCP server.** `plugins/autosteam-studio/runtime/.../server.py` (~1,290 lines, stdlib-only) with workspace sandboxing, path-traversal/symlink guards, credential-stripped subprocess env, atomic runtime bootstrap. **This is portable infrastructure — lift it wholesale.**
- **No model coupling, no open-model path *yet*.** There is no `openai`/`anthropic`/`langchain` dependency in-repo; intelligence is delegated to whatever the host runs. Good (model-agnostic by omission) and bad (no gateway, no local-inference client, no endpoint config).

**Harvest:** the role-file abstraction, the deterministic supervisor pattern, the MCP server, and the human-gate discipline.

### `MandamusCo` — the *governance + approval* half (much stronger than expected)

Mandamus is an **"Agentic Authority Cloud"**: a governance control plane that gates every consequential agent action along the spine `Identity → Mandate → Policy → Capability → Action → Receipt → Reputation`. It is *also* a company that dogfoods its own product (six business agents governed by the same gate). The load-bearing, reusable pieces:

- **The tiered gate (`control-plane/src/gate.mjs`, `registry.mjs`) — the heart of the system.** Pure function `evaluateGate` classifies every action:
  - `T0` observe/read → auto, logged
  - `T1` reversible, low blast-radius → auto
  - **`T1†` bounded-auto** → auto *within* quota + blast + magnitude bounds; crossing any bound **auto-escalates** to T2/T3. (A signature idea worth keeping — it's how you get real autonomy without lights-out risk.)
  - `T2` deterministic-evidence-or-step-up → customer-facing commitment → **passkey (possession)**
  - `T3` always-human genuine presence → irreversible → **iProov Liveness (presence)**
  - `FORBIDDEN` → deny
  - Crucially: **self-asserted evidence from an untrusted agent-scoped caller cannot auto-authorise a T2** — it fails closed to a human. Outward actions are clamped to ≥T2 **in code** regardless of the model's self-assigned tier. The model can only ever *raise* friction, never lower it.
- **Tamper-evident receipts (`ops-receipt.mjs`, `ledger.mjs` + Firestore/Bigtable backends, `kms.mjs`, `anchor.mjs`).** Per-tenant hash-chained, Ed25519-signed receipts; multi-instance-safe atomic append; GCS chain-head anchoring for truncation/rewrite detection. Multi-cloud KMS (Ed25519 + AWS-KMS ECDSA-P256), algorithm-tagged so any cloud verifies ("BYOC").
- **Capabilities / mandates (`mandate.mjs`, `mandate-write.mjs`).** An authorising receipt that is **DPoP-style sender-constrained** (bound to the requester's key thumbprint, single-use, RFC 9396 RAR `authorization_details`, RFC 8693 sub+act delegation). This *is* the "scoped, short-lived, per-action grant" the research literature recommends — already built, standards-aligned.
- **Provider-agnostic agent runtime (`control-plane/src/agent-runtime.mjs`).** `AGENT_BRIEFS` maps each agent to a role string + a whitelist of gate-known action tools; `RUNTIMES = gemini | claude | codex | simulated` (default `gemini-2.0-flash`), keyless simulated fallback. **This is a generic "N LLM brains over one gate" harness — and it already lists `codex`.**
- **A2A orchestration (`interagent.mjs`, `a2a-broker.mjs`, `a2a-server.mjs`).** Declarative cross-agent consultation: a mandate rule with `may_author:false` routes to the owner (CONSULT); `precondition` of kind `resource_gte` (scale needs budget) or `capability` (deploy needs sign-off) makes peers satisfy dependencies. Preconditions and tiers **compose**. Includes an attention-flood guard (bounded step-up queue, dedupe, fail-closed at cap).
- **The passkey + iProov ceremony (`LandingPage/src/lib/verdict.server.ts`, `components/console/iproov-capture.tsx`, `lib/passkey.ts`).** Operator sessions gated to a verified `@iproov.com` IAP identity; the enrolled principal is always server-derived, never client-supplied. **T2 uses WebAuthn passkeys** (`@simplewebauthn`); **T3 adds iProov Liveness** (Web SDK `<iproov-me>`). The workforce PoC requires *both* passkey and face. The biometric-matching backend itself lives in a **sibling WAUTH repo** (`services/wauth-entra-doorkeeper/demo/mandamus-verdict-server.mjs`) — referenced by contract, not in this repo.
- **Doorkeeper (`packages/doorkeeper`, `github-doorkeeper.mjs`).** An npx CLI that wires Codex / Claude Code to the gate over MCP — coding agents (Platform, Developer) act *only* through it. This is the exact bridge your framework needs between a Codex-run role and the governance layer.

**Maturity:** the control-plane is real, tested (289 pass/1 skip), and deployed on Cloud Run (Firestore-backed, Cloud-KMS-signed, GCS-anchored). The *agent company* on top is largely simulation/demo (canned fallbacks, mock partners, observational-only detection). So the **governance substrate is production-shaped; the company is a prototype** — which is precisely the split you want: reuse the substrate, throw away the specific company.

**Harvest:** the entire `control-plane/src` gate+receipt+mandate+A2A spine, the doorkeeper MCP bridge, and the passkey ceremony components. **Do not rebuild these.**

---

## 3. How Claude Cowork actually works (so we copy the right thing)

Because your question hinges on "fine-tuned models vs. prompt theater," this is the load-bearing finding.

- **Architecture:** a persistent **parent agent** receives a task and **spawns per-task child agents**. Children are **isolated** — they cannot read each other's transcripts and (in the observed build) cannot spawn further children. Role differentiation is via the **session/agent abstraction**: each child gets its own context window, system prompt, tool access, and permission set.
- **Models:** a **single base model** (identified in the teardown as a Sonnet-class model), **not distinct fine-tuned per-role models**.
- **Execution environment:** the agent runs inside a **Linux VM** (Apple Virtualization.framework), and the **VM boundary is the security perimeter** — a notable detail because it means Anthropic leans on isolation, not on a hardened in-process sandbox.
- **Human-in-the-loop:** **per-invocation permission gates** (e.g. an MCP tool that asks before accessing a directory). The teardown flags that the *remote phone dispatch* path had **weak authentication** (no MFA/device-binding/presence check in the observed build) — i.e. Anthropic's own consumer product is *not* a model for how to authenticate high-stakes approvals. **You should do better than Cowork here, and passkeys are how.**

**Takeaway for the framework:** copy Cowork's *shape* (single model, parent/child, per-role context + tools + permissions, isolation as the perimeter) and *improve on* its approval authentication (passkeys instead of an unauthenticated phone channel).

---

## 4. Harness choice for open models: Codex vs Claude Agent SDK vs open frameworks

Your framework needs a **runtime** (executes an agent loop, calls tools, sandboxes, spawns subagents) and separately an **orchestration model** (how roles coordinate). Here is the landscape, oriented to *open-weight model support*.

### Tier 1 — production coding-agent harnesses (recommended base)

- **OpenAI Codex** — *primary recommendation.* Native multi-agent: a session spawns specialized subagents in parallel, routes follow-ups, waits, and consolidates. Roles are **declarative TOML** in `.codex/agents/` (`name`, `description`, `developer_instructions`, optional `model`, `sandbox_mode`, `mcp_servers`); ships built-in `default`/`worker`/`explorer` agents; safety controls include `agents.max_threads` (default 6), `agents.max_depth` (default 1), and per-agent sandbox modes (read-only / workspace-write / full). Layered HITL: a guardian intercepts every tool call and escalates sandbox violations (network, out-of-workspace writes) to explicit user approval. **Open models:** Codex is an open-source CLI and can be pointed at an OpenAI-compatible endpoint, so an open-weight model behind a gateway is feasible. **You already run Codex in AutoSteam** (`scripts/codex_exec_autosteam.py`, `.codex/agents/*.toml`) — this is the path of least resistance.
- **Claude Agent SDK / Claude Code** — *strong alternative.* Orchestrates many parallel subagents; background agents via the SDK; an experimental Agent Teams mode. Architecturally **converged with Codex** on the same "one human supervising a team of specialized agents" model. Best if you want to stay Anthropic-native. Open-model support is weaker/indirect (built around Claude), so for an *open-weight-first* mandate, Codex wins.

> Both harnesses run a **single LLM in a loop with accumulating context** — "agentic" behavior emerges from repeated tool-augmented calls, not a separate planner. This confirms you don't need a bespoke planning engine.

### Tier 2 — open-source multi-agent "AI company" frameworks (role libraries, not runtimes)

Useful as **role/orchestration inspiration** or for pure-open deployments, but generally less battle-tested as coding-agent runtimes than Codex/Claude:

- **MetaGPT / ChatDev** — the original "software company as agents" (PM, architect, engineer, QA roles with SOPs). Great role taxonomy; rigid; open-model-capable.
- **CrewAI** — ergonomic role/task/crew abstraction; large community; open-model via LiteLLM. Good for quick company definitions.
- **AutoGen / AG2** — conversational multi-agent; flexible graphs; strong open-model support.
- **LangGraph** — graph/state-machine orchestration with durable execution and checkpoints; the best fit if you want a **typed, resumable orchestration graph** with human-in-the-loop interrupts. Pairs well with any model.
- **OpenHands** — strongest *open* coding-agent runtime (a genuine Codex/Claude-Code alternative you fully control); good if you want to own the harness end-to-end on open weights.
- **CAMEL / AgentScope / smolagents** — research-grade role-play, actor systems, and minimal code-first agents respectively.

**Recommendation:** Use **Codex as the runtime** and borrow **LangGraph's orchestration ideas** (typed state, checkpoints, interrupts) for the supervisor when you outgrow the synchronous pipeline. Keep **OpenHands** in your pocket as the "fully-open, self-hosted harness" escape hatch if you ever need to drop the frontier CLIs entirely.

### Reality check on autonomy

The WORKBench-style evaluations put the best autonomous agents at roughly **~30% completion of real company tasks**, with a sharp split: simple workplace tasks are largely automatable, long-horizon tasks are not. **Design for human-gated, checkpoint-heavy autonomy, not lights-out operation.** This is *why* the HITL layer is central, not a nice-to-have.

---

## 5. Proposed framework architecture — "instantiate any company"

Keep it thin. Four pieces.

### 5.1 The company manifest (the core primitive)

One directory describes a company. The framework reads it and stands up the company.

```
companies/<name>/
  company.yaml          # identity, goal, gates, escalation policy, model routing
  roles/*.toml          # one per role: name, description, instructions, model, sandbox, tools/mcp
  skills/*.md           # natural-language playbooks the roles invoke
  policy/gates.yaml     # which actions require human approval + assurance level
  memory/               # persisted state (files first; Postgres/vector later)
```

- `roles/*.toml` is deliberately the **Codex agent format** so roles are portable to Codex directly, and trivially adaptable to the Claude Agent SDK.
- `company.yaml` declares **model routing** (default open-weight model; premium model for named hard roles) so the same company can run cheap or capable.
- This makes "instantiate any company" a real operation: `framework new-company --from template/software-studio` copies a manifest; editing three files defines a new company.

### 5.2 The supervisor (orchestration)

- Start with the **deterministic synchronous supervisor** you already have (`orchestrator.py`) generalized to read `company.yaml`'s declared role order or a small DAG.
- Each step **spawns a role-agent** in the harness (Codex subagent) with that role's TOML, runs it to completion, captures a structured `AgentResult`, and passes it forward.
- Upgrade path (documented, not built day one): swap the synchronous loop for **LangGraph or Temporal** when a company needs to run continuously, resume after crashes, or wait days for a human. Don't pay this cost until a company demands it.

### 5.3 Memory / state

- **Files first** (as AutoSteam does): structured artifacts on disk under `memory/`, versioned in git. This is honest, auditable, and enough for v1.
- **Add Postgres + a vector store only when a company outgrows files** (long-running LiveOps, cross-session recall). AutoSteam already has the *aspirational* wiring (`docker-compose.yml`, `schema.sql`) — keep it as the documented tier-2, unused until needed.

### 5.4 Tool surface (MCP)

- **Lift the AutoSteam MCP server** as the framework's tool-execution substrate: workspace sandboxing, path-traversal/symlink guards, credential-stripped env, explicit `destructive`/`openWorldHint` annotations, and a single "may touch the network/install deps" bootstrap tool.
- Every **irreversible tool** (deploy, pay, publish, delete, transfer) is annotated as **gated** and routes through the approval service in §6 before executing.

---

## 6. Human-in-the-loop: the approval stack (passkeys, not iProov)

This is where your framework can be genuinely better than Cowork.

### 6.1 The principle

An agent **cannot** perform a WebAuthn ceremony itself — `navigator.credentials.get()` triggers a sandboxed OS biometric/PIN prompt that server-side code has no way to invoke. This is a design guarantee, not a limitation to work around. So the only sound model is: **the agent requests; a human completes a fresh passkey ceremony; the system mints a narrowly-scoped, short-lived token for that one action.**

### 6.2 The flow ("agent requests → human cryptographically approves")

1. **Delegation (once):** the human authenticates with a passkey (WebAuthn, user verification = biometric + PIN) via **OAuth 2.1 Authorization Code + PKCE** and grants the agent a **scoped, temporary** access token. The agent **never holds the passkey or any private key.**
2. **Normal actions:** the agent operates within its scoped token. Low-stakes, allowlisted, reversible actions proceed (mirroring Codex's guardian: safe/allowlisted → auto; sandbox violation → escalate).
3. **High-stakes action (deploy, pay, publish, delete):** the agent's execution **pauses** and raises an approval request. The human completes a **fresh passkey ceremony with UV required** (biometric + PIN — your "biometrics and a secret"). On success, an **elevated, narrowly-scoped, short-lived token** is issued **for that specific operation only**. A fresh passkey signature is treated as **phishing-resistant cryptographic proof of consent** for that operation.
4. **Async / mobile approval:** when the human is away, use **CIBA (OpenID Client-Initiated Backchannel Authentication)** — the agent (as an OAuth client) triggers an out-of-band push to the human's authenticator app; the human approves with their passkey; no credential is exposed to the agent. (Note the known gap: CIBA is client-initiated and doesn't cleanly cover approvals *mid-execution* — handle those with the pause/step-up in step 3.)

### 6.3 Assurance levels (so "highest level" is honestly the highest)

Bind each gated action class to a required assurance level in `policy/gates.yaml`:

| Level | Action class | Required proof |
|---|---|---|
| L0 | Reversible, in-workspace | Scoped token (no prompt) |
| L1 | External read / low-cost write | Passkey session (UV) |
| L2 | Irreversible / spend / publish | **Fresh passkey step-up (UV: biometric + PIN)**, per-action token |
| L3 | Highest (funds transfer, prod delete, legal) | Fresh step-up **+ optional hardware device-bound key** + second approver |

- **Passkey + PIN is sufficient for L2 and, for most companies, L3.** The one dissent in the literature (Yubico, a hardware vendor) argues **hardware device-bound FIDO2 keys** beat synced software passkeys at the very top because the private key can't be extracted via software. Reflect this as an **optional L3 upgrade** (require a device-bound authenticator / hardware key at the top tier), not a dependency. **You do not need iProov at any tier** — keep it only where genuine-presence is a *hard external requirement* (e.g. an AML/KYC-regulated action), not as the default top gate.
- Also note (IETF agent-auth draft): a local **in-agent UI "confirm?" prompt is not authorization** — approval must bind to a verifiable grant from an authorization server. So the passkey ceremony must mint a real, scoped grant, not just flip a boolean. **Mandamus already does this correctly** — its capability mandate is a sender-constrained, single-use, RAR-scoped grant, which is exactly the "verifiable grant" the draft demands.

### 6.4 Mandamus mapping — extract the primitives, don't fork or modify

MandamusCo stays untouched. What Acme takes is the **design and the test cases**, reimplemented as a small Python "Mandamus-Lite" library inside Acme's kernel:

- **Adopt the tier model:** T0/T1/T1†/T2/T3/FORBIDDEN maps onto Acme's A0–A4 assurance tiers (§7.2 of `STRATEGY.md`). The **T1† bounded-auto** idea (auto within quota/blast/magnitude bounds, auto-escalate on crossing) is worth reimplementing — it's how you get real autonomy without lights-out risk.
- **Reimplement, don't reference:** the default-deny gate, the canonical action-intent record, the approval state machine, sender-constrained scoped capabilities, and append-only signed receipts. Port MandamusCo's `gate.mjs`/`mandate.mjs`/`ops-receipt.mjs` behaviors as **language-neutral test vectors**; change any "missing policy" path to default-deny and remove the simulated-success shortcuts. Do this only after a license-compatibility check.
- **Do not change MandamusCo's `gate.mjs`/`registry.mjs`.** The "top tier is passkey, not iProov" decision is expressed in *Acme's* policy (A2 = user-verified passkey; A3 = device-bound hardware key + dual control; iProov = optional enrollment/recovery adapter), not by editing Mandamus.
- **Borrow the pattern, not the runtime, for the doorkeeper:** MandamusCo's `packages/doorkeeper` shows the shape (a Codex/Claude-Code worker acts only through a gate over MCP). Acme's Worker API + policy gateway plays the same role natively.
- **Disposable:** the six-agent roster, the `@iproov.com`-only operator gate, the parent-iProov framing, the canned agent brains.

**Net:** Acme's governance layer is a *from-the-concepts* reimplementation of Mandamus's authority primitives — de-risked (no cross-language dependency, default-deny, no simulated approvals) and owned by Acme.

---

## 7. Build plan

**Phase 0 — Extract the two spines (1–2 weeks).**
(a) Generalize AutoSteam's `orchestrator.py` to read a `company.yaml` + `roles/*.toml`; lift its MCP server as the tool substrate. (b) Fork Mandamus's `control-plane/` into a **framework-governance package** by deleting the six-agent roster and iProov-domain coupling, keeping the gate/receipt/mandate/A2A/doorkeeper spine. Define the manifest schema. Ship one command: `framework run companies/<name>`.

**Phase 1 — Wire supervisor → gate → doorkeeper.**
Make every gated tool call from the supervisor route through the Mandamus gate; coding roles (Codex/Claude Code) act through the doorkeeper. Demo the full path on a throwaway action: agent proposes → gate tiers it → T0/T1 auto, T1† auto-within-bounds, T2+ pauses for approval → receipt sealed to the ledger.

**Phase 2 — Collapse the top tier to passkeys (§6.4).**
In `gate.mjs`/`registry.mjs`, make the T3 presence factor satisfiable by a fresh WebAuthn assertion with `userVerification: required` (biometric + PIN); demote iProov to an optional per-policy presence provider. Demo: an agent tries to "publish," execution pauses, your phone buzzes, you approve with Face ID + PIN, a sender-constrained one-shot capability is minted, the publish proceeds, a signed receipt lands in the ledger — **no iProov in the path.**

**Phase 3 — Re-instantiate AutoSteam on the framework (proof it's generic).**
Port the Steam studio to a `companies/steam-studio/` manifest with zero domain code in the framework core, its release gate now backed by the real Mandamus gate instead of a boolean flag. If AutoSteam runs unchanged behaviorally, the framework is real.

**Phase 4 — Open-model routing.**
Mandamus's runtime already speaks `gemini`/`claude`/`codex`/`simulated`; add an OpenAI-compatible gateway to a strong open-weight model and set it as the `company.yaml` default, premium model reserved for the hardest roles. Verify Codex drives the open model end-to-end through the gate. Keep **OpenHands** noted as the fully-self-hosted fallback runtime.

**Phase 5 — Second company from scratch (real proof).**
Instantiate a company *unrelated* to games (e.g. a research/report shop or an ops company) purely by authoring a manifest. If that works without touching core, the framework is done for v1.

**Later (only when a company needs it):** swap the synchronous supervisor for LangGraph/Temporal (durable, resumable, long-horizon); add Postgres + vector memory; add multi-approver and hardware-key L3.

---

## 8. One-paragraph answer to "do we need Mandamus, or something simpler?"

**Extract Mandamus's authority ideas; drop Mandamus the company; leave the repo untouched.** The "simpler" win isn't a smaller approval service and isn't a fork — it's *not rebuilding the governance concepts you already validated*, reimplemented cleanly in Acme's own stack. Claude Cowork proves roles are prompt-and-tool differentiation over a single base model, not fine-tuned models; Codex (which both repos already drive) is a ready worker harness with declarative role files; and the identity/auth literature agrees a user-verified passkey is phishing-resistant and sufficient for *routine* high-stakes actions, letting iProov drop to an optional enrollment/recovery adapter — while the *truly consequential* tier steps up to a device-bound hardware authenticator plus distinct-person dual control rather than an app PIN. The framework is therefore: **AutoSteam's typed deterministic domain kernel as the first CompanyPack, its privileged actions and any worker (Codex/OpenHands/native) routed through Acme's durable workflow and a from-the-concepts "Mandamus-Lite" default-deny gateway, with WebAuthn transaction authorization at the human gate — over open models behind one profile-based Model API.** Two things you built for two different products turn out to be the two halves of one framework; Acme owns the boundary between them. **This memo is the evidence; `STRATEGY.md` is the plan.**

---

### Sources (from the research sweep; unverified only in the sense that the auto-verifier hit a rate limit — the sources themselves are real and on-point)

- Pluto Security — *Inside Claude Cowork* teardown (parent/child architecture, single Sonnet-class model, VM perimeter, weak phone-dispatch auth).
- *Inside the agent harness: how Codex and Claude Code actually work* (single-LLM loop, guardian HITL, subagent spawning).
- Firecrawl — *Codex multi-agent orchestration* (TOML roles in `.codex/agents/`, built-in agents, `max_threads`/`max_depth`, sandbox modes).
- Corbado — *AI Agents & Passkeys* (agents can't run WebAuthn; OAuth 2.1 + PKCE delegation; step-up with UV as consent proof).
- Yubico — *OpenAI partnership* (hardware device-bound keys argued superior at the top tier; login-only today).
- IETF draft-klrc-aiagent-auth-00 (CIBA for async approval; local UI confirm ≠ authorization; OAuth grants + transaction tokens).
- OpenID Foundation — agent identity whitepaper (CIBA + step-up for sensitive async approvals).
- WORKBench (arXiv 2412.14161) — ~30% autonomous completion; simple-vs-long-horizon split.
- arXiv 2501.06322 — survey of LLM multi-agent collaboration mechanisms (MetaGPT/ChatDev/CAMEL/AutoGen taxonomy).
