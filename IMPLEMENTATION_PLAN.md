# Acme — Implementation Plan

**Companion to `STRATEGY.md`.** This plan turns the strategy into concrete, buildable deliverables. It is deliberately Phase-0-heavy: Phase 0 is what we build now; later phases are scoped enough to sequence but not yet detailed to the file.

**Evidence cutoff / date:** 2026-07-15
**Tracking:** Acme issue #1 · branch `acme-phase0-bootstrap`

---

## 0. Principles that constrain the code (from STRATEGY.md)

These are load-bearing and every module must honor them:

1. **Deterministic kernel, agentic pockets.** Code owns state transitions, budgets, permissions, retries, commits. Models only interpret/synthesize/generate within bounds.
2. **Intent is not authority.** A worker may *emit* an `ActionIntent`; only the gateway may authorize and execute it.
3. **Default-deny.** Missing policy, malformed output, stale approval, ambiguous state → defer or reject, never a canned business action.
4. **Durability before autonomy.** Every long task, retry, timer, human wait, and cancellation must survive process restart.
5. **Provider neutrality at the boundary.** Company definitions name *capability profiles*, not vendor models.
6. **Artifacts over chat.** Handoffs are typed artifacts + provenance, not a growing transcript.
7. **One agent before many.** Multi-agent only when it beats a single-agent baseline on success/cost/latency/policy.

## 1. Target architecture (Phase 0 slice)

```
CompanySpec (yaml) ──▶ Compiler ──▶ CompanyRevision (immutable)
                                        │
                                        ▼
                                   Task ledger + append-only Event log (hash-chained)
                                        │
                             ┌──────────┴───────────┐
                             ▼                      ▼
                        Workflow runner        Operator CLI
                         (durable seam)        (compile / run / inspect)
                             │
                             ▼
                        Worker API ──▶ native worker ──▶ ModelProfile ──▶ Model backend (offline/OpenAI-compat)
                             │
                             ▼
                        ActionIntent ──▶ Default-deny Gateway (Mandamus-Lite) ──▶ [A0/A1 auto | A2+ WAITING_FOR_HUMAN]
                             │
                             ▼
                        ExecutionReceipt ──▶ Event log
```

**What is real in Phase 0:** the compiler, the typed records, the hash-chained ledger, the default-deny gateway with the A0–A4 tier model, the deterministic workflow with crash-resume semantics, a native worker, a model-profile abstraction that defaults to **offline/defer** (no network needed to run or test), and a CLI.

**What is a documented seam (not built yet):** DBOS/Postgres as the durable backend (Phase 1), WebAuthn assertion verification (Phase 1), Codex/OpenHands worker adapters (Phase 2). The workflow runner and ledger expose the interface DBOS will implement, and the gateway's approval step is a real state (`WAITING_FOR_HUMAN`) whose *cryptographic* verification is stubbed to a pluggable `Verifier` returning `deny` by default.

## 2. Repository layout (Phase 0)

```
Acme/
  pyproject.toml
  acme/
    __init__.py
    ids.py                 # deterministic id + canonical JSON + digest helpers
    spec/
      models.py            # CompanySpec Pydantic models
      loader.py            # yaml -> CompanySpec
      jsonschema.py        # emit JSON Schema
    compile/
      compiler.py          # CompanySpec -> CompanyRevision + validation
      errors.py            # typed CompileError with codes
    kernel/
      records.py           # Company, CompanyRevision, Task, Event, ExecutionReceipt, ...
      ledger.py            # append-only hash-chained Event store (sqlite/memory)
      workflow.py          # WorkflowRunner (durable seam) + Step protocol
    gateway/
      intents.py           # ActionIntent + canonical action digest
      policy.py            # A0..A4 tiers, risk classification, default-deny decision
      gate.py              # Gateway: decide -> (auto | require_approval | deny), mint capability, receipt
      verifier.py          # ApprovalVerifier protocol; DenyByDefaultVerifier
    workers/
      api.py               # Worker protocol (task envelope, capability, heartbeats)
      native.py            # bounded deterministic native worker
    models/
      profiles.py          # ModelProfile + registry
      backends.py          # Backend protocol; OfflineDeferBackend; OpenAICompatBackend
    cli.py                 # acme compile | run | inspect | schema
  companies/
    example-studio/company.yaml
  schemas/
    company.schema.json    # generated
  docs/adr/
    ADR-001-dbos-first-durability.md
  tests/
    test_compiler.py
    test_gate.py
    test_ledger.py
    test_workflow.py
```

## 3. Phase 0 deliverables and exit gate

| # | Deliverable | Done when |
|---|---|---|
| 0.1 | CompanySpec models + JSON Schema + example | `acme schema` writes `schemas/company.schema.json`; `example-studio` loads and validates |
| 0.2 | Compiler | Rejects all negative cases in §4; produces a content-addressed immutable `CompanyRevision` |
| 0.3 | Event ledger | Append-only, per-company hash chain; `verify_chain()` detects any tamper/truncation |
| 0.4 | Gateway (Mandamus-Lite) | Default-deny; A0/A1 auto; A2+ → `WAITING_FOR_HUMAN`; capability grants scoped+single-use+TTL; every decision emits a receipt |
| 0.5 | Workflow runner + native worker + model profiles | A deterministic workflow runs a read-only task end-to-end; resumes from the ledger after a simulated crash without duplicating effects |
| 0.6 | CLI | `acme compile`, `acme run`, `acme inspect`, `acme schema` all work on the example |
| 0.7 | Tests + ADR-001 | `pytest` green; ADR-001 records DBOS-first + Temporal graduation triggers |

**Phase 0 exit gate (from STRATEGY.md):** *a process can crash at every step and resume without duplicating a durable effect.* We demonstrate this with a workflow test that replays from the event log and asserts idempotency by digest.

## 4. Compiler validation matrix (default-deny by construction)

The compiler MUST reject, each with a stable error code:

| Code | Rejects |
|---|---|
| `E-REF-ROLE` | workflow step `runAs` an unknown role |
| `E-REF-TOOL` | role grants an unknown tool |
| `E-REF-SCHEMA` | step references an unknown artifact schema |
| `E-REF-WORKFLOW` | goal/entry references an unknown workflow |
| `E-AUTH-NOPOLICY` | role has write authority but no action policy governing it |
| `E-CYCLE-UNBOUNDED` | workflow graph has a cycle without an explicit loop bound |
| `E-IDEMPOTENCY` | an action/tool with side effects lacks idempotency semantics |
| `E-APPROVER` | a high-risk action has no eligible approver role |
| `E-CAP-DEFAULTALLOW` | any capability/grant that is default-allow |
| `E-VERSION` | incompatible pack/schema version |

## 5. Assurance tiers (gateway policy — reconciled with STRATEGY.md §7.2)

| Tier | Examples | Phase-0 gate behavior |
|---|---|---|
| A0 observe | read public data, inspect artifacts | auto, logged |
| A1 bounded internal | reversible draft edits in a versioned workspace | auto within scope/budget; **A1† bounded-auto**: auto within quota/blast/magnitude bounds, auto-escalate on crossing |
| A2 external reversible | stage content, create a draft ticket | `WAITING_FOR_HUMAN`; requires user-verified passkey assertion (verifier stubbed → deny in Phase 0) |
| A3 consequential | send-as-human, deploy prod, pay, delete durable data | `WAITING_FOR_HUMAN`; device-bound hardware authenticator + distinct-person dual control + commit-time revalidation |
| A4 prohibited | unbounded fund movement, self-granting authority, disabling audit | deny; only a separately governed break-glass may change policy |

**Passkey note (carried from the reconciliation):** synced passkeys are not AAL3 (NIST SP 800-63B-4); a device PIN and a biometric are alternative activation factors, not additive. A2 = one user-verified passkey; A3 = hardware-bound + dual control. iProov is an optional enrollment/recovery adapter only, never the per-transaction gate.

## 6. Key interfaces (so Phase 1 slots in cleanly)

```python
# kernel/workflow.py — DBOS implements this later
class WorkflowRunner(Protocol):
    def start(self, revision_id, workflow_id, inputs) -> TaskId: ...
    def step(self, task_id, step_id, fn) -> StepResult: ...   # idempotent by (task_id, step_id)
    def wait_for_human(self, task_id, approval_request) -> None: ...
    def resume(self, task_id) -> None: ...                     # replays from the event log

# gateway/verifier.py — WebAuthn implements this later
class ApprovalVerifier(Protocol):
    def verify(self, approval_request, assertion) -> Decision: ...  # DenyByDefault in Phase 0

# models/backends.py — vLLM/OpenAI-compat implement this later
class ModelBackend(Protocol):
    def complete(self, profile, messages, tools) -> ModelResult: ...  # OfflineDefer in Phase 0
```

## 7. Later phases (sequenced, not yet detailed)

- **Phase 1 — governed effects + human approval.** Swap the in-proc runner/ledger for **DBOS on Postgres**; implement the idempotent executor; implement **WebAuthn** enrollment + assertion verification (real `ApprovalVerifier`) bound one-to-one to the immutable action record; operator inbox UI. *Exit:* no worker performs an external write except through the gateway, and every approved write binds to an immutable action revision.
- **Phase 2 — first CompanyPack + worker portability.** Port **AutoSteam** as the first CompanyPack (keep its deterministic domain kernel; move privileged actions behind the gateway). Add **Codex App Server** and **OpenHands** worker adapters behind the Worker API. Add artifact store + permission-filtered hybrid retrieval; cost/budget enforcement; OpenTelemetry/OpenInference traces; local/open-model baseline via vLLM/SGLang/llama.cpp. *Exit:* the same typed workflow runs on ≥2 worker adapters with equivalent contract-valid artifacts.
- **Phase 3 — measured multi-agent.** Parallel fan-out + typed aggregation, independent verifier workers, delegation-chain capabilities, threshold dual approval + hardware-key policy, optional A2A at external boundaries, Temporal migration ADR if triggers hit. *Exit:* the multi-agent variant beats the single-agent baseline without unacceptable cost/latency/policy regressions.

## 8. What we explicitly do NOT build now

Simulated office chat · self-modifying roles/policies · arbitrary nested agent spawning · a custom vector DB · blockchain/ledger anchoring · universal A2A inside one deployment · model-per-role fine-tunes · iProov on every approval · multi-cloud KMS agility · any automated legal/financial/production authority without explicit policy + human gate · a runtime dependency on MandamusCo's JS control-plane (we reimplement Mandamus-Lite instead, and never modify MandamusCo).
