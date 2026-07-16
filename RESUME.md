# RESUME — pick up here after reboot

**Last session:** 2026-07-16. Everything below is committed and pushed to
`main`. Nothing is lost by a reboot except the local Postgres container and the
venv (both trivially recreated — see below).

## Where things stand

Acme is a working **autonomous-company control plane and HTTP backend**. On
`main` (through PR #6, merge commit `aa01015`):

- Kernel: `CompanySpec` → default-deny compiler → hash-chained event log →
  deterministic workflow runner (crash-resume) → idempotent executor.
- Governance: default-deny capability gateway (A0–A4 tiers), **WebAuthn**
  approvals with distinct-approver quorum (A3 dual control).
- Durability: Postgres event ledger + **DBOS** durable execution (memoization,
  retries, per-company queues). In-process by default; durable when
  `ACME_DATABASE_URL` is set.
- CompanyPacks: `example-studio`, `auto-steam`, `triage-demo` under `companies/`.
- Workers: native + Codex/OpenHands adapters; open-model via OpenAI-compatible
  backend.
- Phase 3: fan-out + independent verify + the **evaluation gate** (`acme eval`).
- Hardening: slug validation, DoS caps, telemetry (scrubbed), untrusted-pack
  guard, tenant isolation. Security-reviewed (one LOW finding fixed).
- **Backend:** FastAPI service via `acme serve`; Docker + compose.

Tests: **93 pass** with Postgres+DBOS, **80** with none (13 infra-gated skips).

## Resume in 4 commands

```bash
cd /Users/johansellstrom/dev/advatar/Acme
git checkout main && git pull

# 1. venv (already on disk at .venv; recreate only if missing)
python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[server,durable,dev]"

# 2. restart the local Postgres (the acme-pg container is gone after reboot)
docker run -d --name acme-pg -e POSTGRES_PASSWORD=acme -e POSTGRES_DB=acme \
  -p 5433:5432 postgres:16-alpine
#   (if it complains the name exists: `docker rm -f acme-pg` first)

# 3. run the tests
. .venv/bin/activate
pytest                                   # 80 passed, 13 skipped (no infra)
DSN=postgresql://postgres:acme@127.0.0.1:5433/acme
ACME_TEST_DATABASE_URL=$DSN ACME_TEST_DBOS_URL=$DSN pytest   # 93 passed

# 4. run the backend
acme serve                               # http://127.0.0.1:8080  (/health, /docs)
#   durable:  ACME_DATABASE_URL=$DSN acme serve
#   docker:   docker compose up --build
```

Full backend/API guide: `docs/BACKEND.md`. Config/ops: `docs/OPERATIONS.md`.
Detailed status + task history: `STATUS.md`.

## What's lost on reboot (and how to recreate)

- **`acme-pg` Postgres container** — ad-hoc, ephemeral test data. Recreate with
  the `docker run` above (or use `docker compose up` which has a persistent
  volume). No real data lived there.
- **`.venv/`** — on disk, survives reboot; recreate only if you wipe it.
- No background processes were left running.

## Next steps (pick up here)

From `STATUS.md` → Next, in rough priority:

1. **Multi-instance approvals UI/state**: persist enrollment-in-progress
   challenges to Postgres (currently in-process in `CompanyService`), and add a
   minimal browser front-end for the passkey enroll/approve ceremony (today it's
   API-only; `tests/test_server.py` drives it headlessly).
2. **Remaining hardening** (`docs/OPERATIONS.md` "Still open"): OpenInference
   spans for model calls, row-level DB tenant enforcement for mutually-distrusting
   tenants, an approval-TTL sweeper.
3. **Optional depth**: run fan-out candidates as durable DBOS steps;
   delegation-chain capabilities.

## One open decision for Johan (not code — strategy)

Whether Acme (this Python engine) stays the primary build, **or** MandamusCo's
existing JS control-plane is extracted in place per its
`docs/COMPANY-IN-A-BOX-PLAN.md`. Both reach the same destination; this session
built out Acme. Unresolved and worth deciding before major further investment.
