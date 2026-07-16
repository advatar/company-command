# Acme backend — where it lives and how to use it

## Where the backend lives

**Acme _is_ the backend.** It is a single long-running Python service — a FastAPI
app (`acme/server/app.py`) wrapping a `CompanyService` (`acme/server/service.py`)
— that you run with `acme serve`. There is no separate server to install: the
same package that provides the CLI and library provides the HTTP backend.

Two deployment shapes:

- **In-process (dev / single node):** `acme serve`. State lives in memory / a
  local SQLite event log. No database required.
- **Durable (production):** set `ACME_DATABASE_URL` to a Postgres DSN. The event
  log, approvals, and credentials move to Postgres; work steps run as durable
  DBOS steps. DBOS also creates its own system database (`<db>_dbos_sys`)
  alongside yours. Run N replicas against one Postgres — they share the ledger
  and an approval opened on one is completable on another.

So the backend "lives" wherever you run the `acme` process; its **durable state
lives in Postgres**. Companies (the business logic) live as **CompanyPacks** in a
directory (`ACME_COMPANIES_DIR`, default `./companies`) that the service loads at
startup.

```
                 ┌───────────────────────────┐
  HTTP client →  │  acme serve (FastAPI)      │
  (UI / curl)    │  CompanyService            │
                 │   ├─ per-company gateway,  │
                 │   │   executor, runner     │
                 │   ├─ WebAuthn verifier     │
                 │   └─ DBOS durable engine   │
                 └──────────┬────────────────┘
                            │ event log, approvals, credentials
                            ▼
                    ┌──────────────┐     companies/  (CompanyPacks:
                    │  Postgres    │      company.yaml + pack.py)
                    └──────────────┘
```

## Install

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[server,durable,dev]"     # server = FastAPI; durable = Postgres+DBOS
```

(Only need `[server]` to run the API in-process; add `[durable]` for Postgres.)

## Run

### In-process
```bash
acme serve --host 0.0.0.0 --port 8080 --companies companies
curl localhost:8080/health
```

### Durable (Docker Compose — Acme + Postgres)
```bash
docker compose up --build          # API on :8080, Postgres on :5433
```
Or point a local process at Postgres:
```bash
export ACME_DATABASE_URL=postgresql://postgres:acme@127.0.0.1:5433/acme
acme serve
```

## HTTP API

| Method + path | Purpose |
|---|---|
| `GET /health` | status, durable flag, loaded companies |
| `GET /companies` | list companies (workflows, roles) |
| `POST /companies/{c}/tasks` | start a workflow — body `{workflow, inputs}` → task state + artifacts |
| `GET /companies/{c}/tasks/{id}` | task state reconstructed from the event log |
| `GET /companies/{c}/approvals` | the approval inbox (pending, with challenge) |
| `POST /companies/{c}/credentials/options` | WebAuthn registration options for a principal |
| `POST /companies/{c}/credentials` | verify + store a passkey registration |
| `POST /companies/{c}/approvals/{digest}/options` | WebAuthn challenge to sign for an approval |
| `POST /companies/{c}/approvals/submit` | submit a signed assertion → authorizes + executes |
| `POST /companies/{c}/eval` | evaluation gate — body `{baseline, variant}` |
| `GET /companies/{c}/events` | tamper-evident audit log |

Interactive docs: `http://localhost:8080/docs` (FastAPI/OpenAPI).

### The governed lifecycle over HTTP

```bash
C=auto-steam
# 1. start — parks at the human gate
curl -s -XPOST localhost:8080/companies/$C/tasks -d '{"workflow":"ship-title"}' -H content-type:application/json
# -> {"task_id": "...", "state": "WAITING_FOR_HUMAN", "waiting_on": {"intent_digest": "sha256:...", "step": "release"}}

# 2. enroll a passkey (one-time): browser calls navigator.credentials.create() with:
curl -s -XPOST localhost:8080/companies/$C/credentials/options -d '{"principal":"human:studio-lead"}' -H content-type:application/json
# ... then POST the credential to /companies/$C/credentials

# 3. approve: browser calls navigator.credentials.get() with the challenge from:
curl -s -XPOST localhost:8080/companies/$C/approvals/<digest>/options
# ... then POST {task_id, workflow, step, assertion} to /companies/$C/approvals/submit
# -> {"state": "SUCCEEDED"}  (the effect executed exactly once, through the gateway)

# 4. audit
curl -s localhost:8080/companies/$C/events
```

An **agent can never complete the ceremony** — steps 2–3 require a human passkey
with user verification (biometric/PIN). The client half is a WebAuthn browser
flow; `tests/test_server.py` drives it headlessly with a software authenticator.

## Configuration (env)

See `docs/OPERATIONS.md`. Key ones: `ACME_DATABASE_URL` (durable on/off),
`ACME_COMPANIES_DIR`, `ACME_RP_ID` / `ACME_RP_ORIGIN` (WebAuthn — set these to
your real domain in production), `ACME_MODEL_URL` (open-model endpoint).

## Adding a company

Drop a directory in `ACME_COMPANIES_DIR`:

```
companies/my-co/
  company.yaml          # roles, workflows, actions, approval tiers
  pack.py               # SKILLS (step logic) + HANDLERS (effects) [+ SCENARIOS]
```

Restart the service; it appears in `GET /companies`. `pack.py` is executed as
Python, so only load packs you control (the loader refuses untrusted packs).
