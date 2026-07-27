# RESUME — pick up here after reboot

## 2026-07-27 integration handoff

Company Command now has two additional optional workers:

- `comcmd.workers.loop.LoopWorker` runs bounded Codex/Claude repository work in
  persistent task/step-specific isolated clones. Acme owns providers, limits,
  state paths, and environment exposure. It returns Loop state plus Git
  base/head/diff evidence, resumes interrupted runs, and reuses terminal states.
- `comcmd.workers.openworker.OpenWorker` connects to a local OpenWorker session
  in forced read-only `plan` mode and returns artifacts without delegating
  effect authorization.

The workflow kernel now handles `WorkerResult(status="deferred")` correctly:
the task becomes `FAILED_RETRYABLE`, evidence is recorded, and the step is not
emitted as `step_succeeded`. Durable work-step memoization preserves worker
usage and questions as well as status/artifact.

Loop is available programmatically through `build_runner(..., worker=...)` and
from `comcmd run --worker loop`. Install the optional dependency with
`pip install -e ".[loop]"`. Consequential effects remain separate
`ActionIntent`/human-gate steps; worker environment filtering is defense in
depth and does not replace OS/container network and filesystem isolation.

Validation baseline on 2026-07-27:

```bash
cd /Users/johansellstrom/dev/advatar/Acme
.venv/bin/pytest tests --disable-warnings
```

Expected: 90 passed, 13 infrastructure-gated skips. Loop's own suite has 18
passing tests. No live paid Codex/Claude/OpenWorker session was used in tests.

Next useful work:

1. Add declarative per-role worker routing; the current CLI selects one worker
   for all work steps in a run.
2. Run authorized end-to-end smoke tests against real Codex, Claude, and
   OpenWorker installations inside the intended worker sandbox.
3. Add cancellation/lease propagation from Acme into active Loop subprocesses.
4. Publish `agent-loop` before relying on the `comcmd[loop]` extra from PyPI.

**Last session:** 2026-07-16. Everything below is committed and pushed to
`main`. Nothing is lost by a reboot except the local Postgres container and the
venv (both trivially recreated — see below).

## Where things stand

Company Command is a working **autonomous-company control plane and HTTP backend**. On
`main` (through PR #6, merge commit `aa01015`):

- Kernel: `CompanySpec` → default-deny compiler → hash-chained event log →
  deterministic workflow runner (crash-resume) → idempotent executor.
- Governance: default-deny capability gateway (A0–A4 tiers), **WebAuthn**
  approvals with distinct-approver quorum (A3 dual control).
- Durability: Postgres event ledger + **DBOS** durable execution (memoization,
  retries, per-company queues). In-process by default; durable when
  `COMCMD_DATABASE_URL` is set.
- CompanyPacks: `example-studio`, `auto-steam`, `triage-demo` under `companies/`.
- Workers: native + Codex/OpenHands adapters; open-model via OpenAI-compatible
  backend.
- Phase 3: fan-out + independent verify + the **evaluation gate** (`comcmd eval`).
- Hardening: slug validation, DoS caps, telemetry (scrubbed), untrusted-pack
  guard, tenant isolation. Security-reviewed (one LOW finding fixed).
- **Backend:** FastAPI service via `comcmd serve`; Docker + compose.

Tests: **93 pass** with Postgres+DBOS, **80** with none (13 infra-gated skips).

## Resume in 4 commands

```bash
cd /Users/johansellstrom/dev/advatar/Company Command
git checkout main && git pull

# 1. venv (already on disk at .venv; recreate only if missing)
python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[server,durable,dev]"

# 2. restart the local Postgres (the comcmd-pg container is gone after reboot)
docker run -d --name comcmd-pg -e POSTGRES_PASSWORD=comcmd -e POSTGRES_DB=comcmd \
  -p 5433:5432 postgres:16-alpine
#   (if it complains the name exists: `docker rm -f comcmd-pg` first)

# 3. run the tests
. .venv/bin/activate
pytest                                   # 80 passed, 13 skipped (no infra)
DSN=postgresql://postgres:comcmd@127.0.0.1:5433/comcmd
COMCMD_TEST_DATABASE_URL=$DSN COMCMD_TEST_DBOS_URL=$DSN pytest   # 93 passed

# 4. run the backend
comcmd serve                               # http://127.0.0.1:8080  (/health, /docs)
#   durable:  COMCMD_DATABASE_URL=$DSN comcmd serve
#   docker:   docker compose up --build
```

Full backend/API guide: `docs/BACKEND.md`. Config/ops: `docs/OPERATIONS.md`.
Detailed status + task history: `STATUS.md`.

## What's lost on reboot (and how to recreate)

- **`comcmd-pg` Postgres container** — ad-hoc, ephemeral test data. Recreate with
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

Whether Company Command (this Python engine) stays the primary build, **or** MandamusCo's
existing JS control-plane is extracted in place per its
`docs/COMPANY-IN-A-BOX-PLAN.md`. Both reach the same destination; this session
built out Company Command. Unresolved and worth deciding before major further investment.
