# Acme

A small, model-neutral **autonomous-company control plane**. Acme compiles a
declarative `CompanySpec` into durable work, runs that work through replaceable
agent workers, mediates every side effect through a **default-deny capability
gateway**, and pauses durably for **authenticated human approval** when policy
requires it. Roles are bundles of skills, permissions, data scopes, model
profiles, budgets, and escalation rules — not simulated employees.

- **Plan:** [`STRATEGY.md`](STRATEGY.md) (canonical) · research: [`STRATEGY-RESEARCH-MEMO.md`](STRATEGY-RESEARCH-MEMO.md)
- **Build:** [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) · [`docs/adr/`](docs/adr) · progress in [`STATUS.md`](STATUS.md)

## Status — Phase 0 (walking skeleton)

Implemented and tested:

- `CompanySpec` models + JSON Schema (`acme/spec`, `acme schema`)
- Manifest **compiler** with default-deny validation (`acme/compile`)
- Append-only **hash-chained event ledger** (`acme/kernel/ledger.py`)
- Default-deny **capability gateway** ("Mandamus-Lite") with A0–A4 assurance
  tiers, bounded-auto, and a deny-by-default approval verifier (`acme/gateway`)
- Deterministic **workflow runner** with crash-resume (`acme/kernel/workflow.py`)
- **Worker API** + bounded native worker; **model profiles** with an
  offline-defer backend and an OpenAI-compatible backend (`acme/workers`, `acme/models`)
- Operator **CLI**: `compile`, `run`, `inspect`, `schema`

Phase 0 exit gate — *a process can crash at every step and resume without
duplicating a durable effect* — is demonstrated by `tests/test_workflow.py`.

## Quickstart

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"          # or: pip install pydantic pyyaml pytest

pytest                            # 25 tests
python -m acme.cli compile companies/example-studio
python -m acme.cli run     companies/example-studio validate-product
python -m acme.cli schema -o schemas/company.schema.json
```

`run` drives the example workflow to its `humanGate` and parks it in
`WAITING_FOR_HUMAN` — because the Phase 0 approval verifier is deny-by-default.
Phase 1 wires the real WebAuthn verifier and DBOS/Postgres durability (see
[ADR-001](docs/adr/ADR-001-dbos-first-durability.md)).

## Layout

```
acme/
  spec/       CompanySpec models, loader, JSON Schema
  compile/    manifest compiler + typed errors (default-deny)
  kernel/     records, hash-chained ledger, workflow runner
  gateway/    ActionIntent, A0–A4 policy, default-deny gate, approval verifier
  workers/    Worker API + bounded native worker
  models/     capability profiles + backends (offline-defer / OpenAI-compat)
  cli.py
companies/example-studio/company.yaml
tests/
```

## Non-goals (Phase 0)

Simulated office chat · self-modifying roles/policies · arbitrary nested agent
spawning · a custom vector DB · a runtime dependency on MandamusCo (Acme
reimplements a small "Mandamus-Lite" and never modifies MandamusCo). See
`IMPLEMENTATION_PLAN.md` §8.
