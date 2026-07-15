# Acme operations runbook

## Configuration (environment)

| Variable | Meaning | Default |
|---|---|---|
| `ACME_DATABASE_URL` | Postgres DSN. Set → **durable** mode (Postgres ledger + DBOS). Unset → in-process. | unset |
| `ACME_LEDGER_URL` | Override the ledger DSN separately from the DBOS DSN. | `ACME_DATABASE_URL` |
| `ACME_RP_ID` / `ACME_RP_ORIGIN` | WebAuthn relying-party id / expected origin. | `localhost` / `https://localhost` |
| `ACME_MODEL_URL` / `ACME_MODEL_KEY` / `ACME_MODEL_MAP` | OpenAI-compatible model endpoint + key + `profile=model,...` map. | unset (offline-defer) |
| `ACME_LOG_LEVEL` / `ACME_DBOS_LOG_LEVEL` | Log verbosity. | `INFO` / `WARNING` |

Secrets (DB password, model key) come from the environment/secret manager, never
from `company.yaml`. Logs never contain challenges, assertions, or capabilities.

## Running

```bash
make install           # venv + deps (.[dev,durable])
make test              # in-process suite
make pg-up             # local Postgres 16 in Docker (port 5433)
make test-infra        # full durable suite (Postgres + DBOS)
make run               # in-process AutoSteam
make run-durable       # durable AutoSteam (needs Postgres)
```

## Durable deployment

1. Provision Postgres (managed or self-hosted). DBOS creates its own system
   database (`<db>_dbos_sys`) alongside the application DB.
2. Set `ACME_DATABASE_URL`. On start, Acme uses the Postgres hash-chained ledger,
   runs work steps as durable DBOS steps, and persists approvals/credentials.
3. Multiple app instances can share one Postgres: appends are serialized per
   company with a transaction-scoped advisory lock, and an approval opened on one
   instance can be completed on another (`PgApprovalStore` / `PgCredentialStore`).

## Human-in-the-loop approval

- List pending approvals: `acme approvals <ledger-url> <company>` (reads the log;
  works cross-process against a Postgres DSN).
- An A2 action needs one user-verified passkey; A3 needs a device-bound key and
  ≥2 distinct approvers (dual control). iProov is optional, for
  enrollment/recovery only — never the per-transaction gate.

## Health & audit

- **Chain integrity:** `acme inspect <ledger-url> <company>` prints events and
  reports `chain valid`. A `false` means truncation/rewrite — investigate before
  trusting downstream state.
- **Recovery:** in durable mode, a crashed process resumes on restart — the
  Postgres log reconstructs task state and DBOS replays memoized steps. No
  duplicate effects (idempotent executor keyed by action digest).

## Hardening (implemented)

- **Tenant safety:** company names must be safe slugs (`E-SLUG`); the event log,
  approvals, and action digests are company-scoped (isolation tests in
  `tests/test_isolation.py`, incl. shared-Postgres).
- **Untrusted packs:** `load_pack(dir, trusted=False)` refuses to execute a
  pack's `pack.py` (arbitrary code) — load customer-supplied manifests this way
  and supply skills/handlers out-of-band. Only `trusted=True` runs pack code.
- **DoS guards:** fan-out and verifier counts are capped at compile time
  (`E-FANOUT`/`E-VERIFY`).
- **Per-company queues:** `DbosEngine.company_queue(company, concurrency=...)` /
  `enqueue(..., per_company=True)` — one tenant cannot starve others.
- **Telemetry:** set `ACME_OTEL=1` (with `pip install '.[otel]'`) to export
  gateway decisions and spans via OpenTelemetry; secrets are scrubbed and the
  hash-chained event log remains the authoritative audit trail.

## Still open

- OpenInference span conventions for model calls; a reference collector wiring.
- Row-level DB enforcement of tenant scoping (today isolation is by company key +
  tests); per-tenant credentials/roles if hosting mutually-distrusting tenants.
- Approval-store TTL sweeper for expired rows (currently filtered on read).
