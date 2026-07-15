# Acme architecture

Acme is a small, model-neutral **company control plane**: it compiles a declared
`CompanySpec` into durable work, runs that work through replaceable workers,
mediates every side effect through a default-deny capability gateway, and pauses
durably for authenticated human approval when policy requires it.

## The unit of operation

```
goal → workflow → task → step → artifact / ActionIntent → policy decision
     → (human approval) → verified effect → receipt → event log
```

Chat is never authoritative state; the append-only event log is. Roles are
bundles of skills/tools/scopes/budgets, not simulated employees.

## Layers

| Layer | Module | Responsibility |
|---|---|---|
| Spec + compile | `acme/spec`, `acme/compile` | Typed `CompanySpec`; default-deny compiler → immutable `CompanyRevision` |
| Event log | `acme/kernel/ledger.py`, `ledger_pg.py` | Append-only, per-company hash chain (SQLite or Postgres) — the source of truth |
| Workflow | `acme/kernel/workflow.py` | Deterministic runner; crash-resume by replaying the log; human gates |
| Durable exec | `acme/kernel/dbos_engine.py` | DBOS step memoization, retries, queues (Postgres) |
| Gateway | `acme/gateway` | `ActionIntent` → A0–A4 tiers → default-deny decision; scoped capabilities; receipts |
| Approval | `acme/gateway/webauthn_verifier.py`, `approvals.py`, `stores_pg.py` | WebAuthn assertion bound 1:1 to the action digest; distinct-approver quorum; durable stores |
| Executor | `acme/kernel/executor.py` | Performs an authorized effect exactly once (idempotent by digest) |
| Workers | `acme/workers` | Native worker; Codex/OpenHands CLI adapters |
| Models | `acme/models` | Capability profiles → backends (offline-defer / OpenAI-compatible) |
| Pack | `acme/pack.py` | A company = `company.yaml` + `pack.py` (SKILLS/HANDLERS) |

## Execution modes

- **In-process (default):** SQLite/in-memory ledger; the runner replays the log
  to resume. Crash-resume and idempotency hold; single node.
- **Durable (production):** set `ACME_DATABASE_URL`. The event log moves to
  Postgres (advisory-locked atomic hash-chained appends), work steps run as
  memoized DBOS steps (survive restart, auto-retry), and approvals/credentials
  persist so an approval opened on one node can be completed on another. The
  governance path (gateway, gates, executor) is identical in both modes — only
  the backends change (`build_runner(..., durable_engine=...)`).

## The approval invariant

An agent can never complete a WebAuthn ceremony. A worker emits an
`ActionIntent`; the gateway classifies it; A2/A3 open a human approval bound to
the action digest via a fresh challenge. A human signs with a passkey
(user-verification required); the verifier checks challenge/origin/UV and returns
the principal; distinct principals accumulate to quorum (A3 = dual control). Only
then is a scoped, single-use capability minted and the executor runs the effect
once. Passkeys replace iProov for routine approvals; the highest tier uses a
device-bound authenticator + distinct-person dual control. Local UI confirmation
is never authorization — the mint is.

## Security posture

- **Default-deny everywhere:** unknown action, missing policy, malformed output,
  stale/expired approval → defer or reject.
- **Meta-governance is engine-locked:** the reserved `acme.*` action namespace
  cannot be invented or weakened by a company (`E-META-LOCKED`, `E-TIER-LOWERED`)
  — no self-authorized de-escalation.
- **Tamper-evident:** every event is sealed into a per-company hash chain;
  `verify_chain` detects truncation/rewrite.
- **Least privilege:** capabilities are scoped, single-use, and TTL-bound.
