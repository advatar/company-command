# Acme

A small, model-neutral **autonomous-company control plane**. Acme compiles a
declarative `CompanySpec` into durable work, runs that work through replaceable
agent workers, mediates every side effect through a **default-deny capability
gateway**, and pauses durably for **authenticated human approval** when policy
requires it. Roles are bundles of skills, permissions, data scopes, model
profiles, budgets, and escalation rules — not simulated employees.

- **Plan:** [`STRATEGY.md`](STRATEGY.md) (canonical) · research: [`STRATEGY-RESEARCH-MEMO.md`](STRATEGY-RESEARCH-MEMO.md)
- **Build:** [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) · [`docs/adr/`](docs/adr) · progress in [`STATUS.md`](STATUS.md)

## Status — Phase 0 + Phase 1 (governed effects + human approval)

Implemented and tested (**40 tests**):

- `CompanySpec` models + JSON Schema (`acme/spec`, `acme schema`)
- Manifest **compiler** with default-deny validation (`acme/compile`)
- Append-only **hash-chained event ledger** (`acme/kernel/ledger.py`)
- Default-deny **capability gateway** ("Mandamus-Lite") with A0–A4 assurance
  tiers, bounded-auto, scoped single-use capabilities, receipts (`acme/gateway`)
- **WebAuthn approval** (`acme/gateway/webauthn_verifier.py`, `enrollment.py`,
  `approvals.py`): assertion bound 1:1 to the immutable action digest, UV
  required, phishing-resistant origin binding, **distinct-approver quorum**
  (A3 dual control). Deny-by-default when unconfigured.
- **Idempotent executor** (`acme/kernel/executor.py`): an authorized effect
  runs exactly once; replay after a crash re-runs nothing.
- Deterministic **workflow runner** with crash-resume and an approval/resume
  path (`acme/kernel/workflow.py`)
- **Worker API** + bounded native worker; **model profiles** with an
  offline-defer backend and an OpenAI-compatible backend (`acme/workers`, `acme/models`)
- Operator **CLI**: `compile`, `run`, `inspect`, `schema`, `approvals`

- **Postgres durable ledger** (`acme/kernel/ledger_pg.py`, `make_ledger`):
  the hash-chained event log on Postgres with per-company advisory-locked
  atomic appends, so crash-resume is durable **across processes/machines**. The
  runner and CLI run unchanged against it.

Exit gates met: Phase 0 crash-resume (`tests/test_workflow.py`); Phase 1 — no
worker writes except through the gateway, every approved write bound to an
immutable action revision (`tests/test_approval_e2e.py`), and durable execution
across processes on Postgres (`tests/test_ledger_pg.py`). Remaining: DBOS
workflow primitives (queues/timers/leases/HA) layered on the Postgres ledger,
honestly gated in `acme/kernel/durable.py` (see
[ADR-001](docs/adr/ADR-001-dbos-first-durability.md)).

## Quickstart

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"          # or: pip install pydantic pyyaml pytest

pytest                            # 56 tests (63 with Postgres+DBOS enabled)
python -m acme.cli compile companies/example-studio
python -m acme.cli run      companies/auto-steam ship-title      # a second, different company
python -m acme.cli run      companies/example-studio validate-product --ledger acme.sqlite
python -m acme.cli approvals acme.sqlite example-studio
python -m acme.cli schema -o schemas/company.schema.json
python -m acme.cli eval companies/triage-demo --baseline triage-single --variant triage-panel
```

The `eval` command is the **multi-agent gate**: it runs a single-agent baseline
against a fan-out+verify variant over scenarios and only reports `PROMOTE` if the
multi-agent variant beats the baseline on success without unacceptable cost /
latency / policy regressions. Adding agents that don't win is theater — the gate
says so.

A **CompanyPack** is a directory: a declared `company.yaml` plus an optional
`pack.py` supplying the company's deterministic domain skills and effect
handlers. `companies/example-studio` and `companies/auto-steam` are two very
different companies on the same kernel — the governance core is generic, the
domain lives in the pack.

`run` drives the example workflow to its `humanGate` and parks it in
`WAITING_FOR_HUMAN`; `approvals` shows the pending action and its challenge. A
verified WebAuthn approval (`WorkflowRunner.approve_step`) authorizes the effect
through the gateway and drives the task to `SUCCEEDED` — see
`tests/test_approval_e2e.py` for the full ceremony. The remaining Phase 1 item
is DBOS/Postgres durability (see [ADR-001](docs/adr/ADR-001-dbos-first-durability.md)).

## Layout

```
acme/
  spec/       CompanySpec models, loader, JSON Schema
  compile/    manifest compiler + typed errors (default-deny)
  kernel/     records, hash-chained ledger, workflow runner, idempotent executor, durable seam
  gateway/    ActionIntent, A0–A4 policy, default-deny gate, approvals+quorum,
              WebAuthn verifier, credential enrollment
  workers/    Worker API + native worker + Codex/OpenHands CLI adapters
  models/     capability profiles + backends (offline-defer / OpenAI-compat)
  pack.py     CompanyPack loader + build_runner wiring
  cli.py
companies/    example-studio/ and auto-steam/ (company.yaml [+ pack.py])
tests/        + tests/support/ (software WebAuthn authenticator)
```

## Non-goals (Phase 0)

Simulated office chat · self-modifying roles/policies · arbitrary nested agent
spawning · a custom vector DB · a runtime dependency on MandamusCo (Acme
reimplements a small "Mandamus-Lite" and never modifies MandamusCo). See
`IMPLEMENTATION_PLAN.md` §8.
