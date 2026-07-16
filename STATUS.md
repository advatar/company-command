# Acme Status

## Autonomous Company Framework Strategy

- [x] Assess scope and identify the two reference implementations to review.
- [x] Create [GitHub issue #1](https://github.com/advatar/Acme/issues/1) documenting the research questions, evidence standards, and delivery plan.
- [x] Audit MandamusCo architecture, role model, orchestration, approvals, and reusable components.
- [x] Audit autonomous-steam-studio architecture, role model, orchestration, approvals, and reusable components.
- [x] Research Claude Cowork and Codex orchestration using current public evidence, separating facts from inference.
- [x] Review open-model and non-frontier-lab agent orchestration, durable execution, identity, evaluation, and human-in-the-loop approaches.
- [x] Define the recommended generic company-instantiation architecture and its minimum viable implementation roadmap.
- [x] Analyze passkey plus PIN approval assurance and document where stronger controls are required.
- [x] Write and source the strategy document (`STRATEGY.md`) and research memo (`STRATEGY-RESEARCH-MEMO.md`).
- [x] Verify document links, internal consistency, and repository state.

## Phase 0 — walking skeleton (branch `acme-phase0-bootstrap`)

- [x] `IMPLEMENTATION_PLAN.md` derived from STRATEGY.md §11.
- [x] Python project scaffold (`pyproject.toml`, `acme/` package, pytest).
- [x] `CompanySpec` Pydantic models, YAML loader, JSON Schema emitter.
- [x] Manifest compiler with default-deny validation (10 error codes) and content-addressed `CompanyRevision`.
- [x] Append-only, per-company hash-chained event ledger (SQLite) with tamper detection.
- [x] Default-deny capability gateway ("Mandamus-Lite"): `ActionIntent` + canonical digest, A0–A4 tiers, A1 bounded-auto, deny-by-default approval verifier, scoped single-use capabilities, receipts.
- [x] Deterministic workflow runner with crash-resume; Worker API + bounded native worker; model profiles (offline-defer + OpenAI-compatible backends); operator CLI.
- [x] Test suite (25 passing): compiler negatives, ledger chain/tamper, gate tiers/deny/dual-control/bounded-auto, workflow crash-resume + idempotency.
- [x] `ADR-001` (DBOS-first durability, Temporal graduation triggers).

**Phase 0 exit gate met:** a process can crash at every step and resume without duplicating a durable effect (`tests/test_workflow.py`).

## Phase 1 — governed effects + human approval (branch `acme-phase0-bootstrap`)

- [x] Real **WebAuthn `ApprovalVerifier`** (`acme/gateway/webauthn_verifier.py`) + credential enrollment (`enrollment.py`): verifies an authentication assertion bound 1:1 to the immutable action digest via a fresh challenge; enforces origin/RP binding, **user-verification required**, sign-count monotonicity. Deny-by-default when unconfigured.
- [x] **Approval sessions + quorum** (`acme/gateway/approvals.py`): distinct-approver accumulation; A3 requires ≥2 distinct principals (dual control); TTL expiry; single-use.
- [x] **Idempotent executor** (`acme/kernel/executor.py`): performs an authorized effect exactly once (keyed by action digest); capability↔digest binding; replay after crash re-runs nothing.
- [x] **Workflow approval/resume** (`WorkflowRunner.approve_step`): a `humanGate` opens an approval, parks the task, and on quorum authorizes → executes → advances to `SUCCEEDED`.
- [x] **Operator inbox CLI** (`acme approvals <ledger> <company>`): lists pending approvals from the ledger (read-only, cross-process).
- [x] Tests: WebAuthn verify (valid/wrong-challenge/unknown-cred/no-UV/wrong-origin), executor idempotency, dual-control quorum, full approval ceremony (**40 tests passing**). Software authenticator test helper in `tests/support/`.
- [x] **Postgres durable event ledger** (`acme/kernel/ledger_pg.py`, `make_ledger`): hash-chained event log on Postgres with per-company advisory-locked atomic appends → crash-resume durable **across processes/machines**. Same interface as the SQLite ledger; the WorkflowRunner and CLI run unchanged against it. Conformance suite (incl. the Phase 0 crash-resume gate + tamper detection) passes on real Postgres (`tests/test_ledger_pg.py`).
- [x] **Durability seam** (`acme/kernel/durable.py`), honestly gated: the durable log is done; DBOS *workflow primitives* (queues/timers/leases/HA) are the remaining layer and `require_durable_backend` fails loudly rather than silently degrading.

**Phase 1 exit gate met:** no worker performs an external write except through the gateway; every approved write binds to an immutable action revision (`tests/test_approval_e2e.py`); and durable execution is proven across processes on Postgres (`tests/test_ledger_pg.py`, plus a 3-process CLI demo). **44 tests** pass with Postgres enabled (40 + 4 PG); 40 pass with PG skipped.

- [x] **DBOS durable execution engine** (`acme/kernel/dbos_engine.py`): work-step pipelines run as DBOS steps keyed by the Acme task id — durable step **memoization** (a completed step never re-runs on resume), automatic step **retries**, and a durable **queue**. Behind the `durable.py` seam (`make_durable_engine`), gated on a Postgres DSN. Tested against Postgres (`tests/test_dbos.py`): memoization/resume, transient-retry recovery, durable queue. **47 tests** pass with PG+DBOS enabled.

## Phase 2 — CompanyPacks, worker portability, open models (branch `acme-phase0-bootstrap`)

- [x] **CompanyPack** loader + run wiring (`acme/pack.py`): a company is a directory (`company.yaml` + optional `pack.py` exposing `SKILLS`/`HANDLERS`); `build_runner` wires compile → ledger → gateway → native worker(skills) → executor(handlers). CLI `run` uses the pack.
- [x] **AutoSteam as the first CompanyPack** (`companies/auto-steam/`): a second, unrelated company (market → design → qa → compliance → release humanGate) runs end-to-end on the same kernel with deterministic domain skills and a gateway-guarded `steam.publish`. Proves the framework is generic; nothing studio-specific lives in `acme/*` (`tests/test_autosteam_pack.py`).
- [x] **Codex + OpenHands worker adapters** (`acme/workers/cli_agents.py`): implement the same `Worker` contract; build a prompt from the envelope, shell out to the agent CLI, parse the result. Availability-gated (defer safely when the binary is absent); prompt/parse logic unit-tested via injected runner (`tests/test_cli_workers.py`).
- [x] **Open-model baseline**: `OpenAICompatBackend` verified end-to-end against an in-process mock OpenAI-compatible server (same protocol as vLLM/SGLang/llama.cpp), incl. fail-closed on unreachable endpoint (`tests/test_openmodel.py`).
- [x] **Locked engine catalog + functional domain** (from the MandamusCo Company-in-a-Box plan §5): the compiler forbids inventing/weakening reserved `acme.*` meta-governance actions (`E-META-LOCKED`, `E-TIER-LOWERED` — no self-authorized de-escalation); optional `domain` (software/ops/money/legal) on actions.

**63 tests** pass with PG+DBOS enabled (56 + 7 infra); 56 pass with none. Phase 2 established: the same typed kernel runs two distinct companies, routes steps to native/Codex/OpenHands workers, and drives open models.

## Production-grade unification (branch `acme-phase0-bootstrap`)

- [x] **Unified execution**: `WorkflowRunner` runs work steps durably-memoized on DBOS when a durable engine is configured, through the **same** gateway/human-gate/executor over the Postgres ledger. `build_runner(..., durable_engine=...)`; CLI `run --durable` (or `ACME_DATABASE_URL`). Verified: AutoSteam runs durably end-to-end and publishes once (`tests/test_durable_e2e.py`).
- [x] **Config layer** (`acme/config.py`): env-driven `Settings` (`ACME_DATABASE_URL`, `ACME_RP_ID/ORIGIN`, `ACME_MODEL_*`); DSN present → durable mode.
- [x] **Postgres-backed credential + approval stores** (`acme/gateway/stores_pg.py`): enrollment and pending approvals persist so an approval opened on one instance is completed on another — verified cross-instance (`tests/test_stores_pg.py`).
- [x] **Structured logging** (`acme/log.py`): gateway logs decisions by identifier only (never challenge/assertion/capability); DBOS quieted.
- [x] **CI + Makefile + docs**: GitHub Actions runs both suites with a Postgres service (`.github/workflows/ci.yml`); `Makefile` (install/test/test-infra/pg-up/run-durable); `docs/ARCHITECTURE.md` + `docs/OPERATIONS.md` runbook.

**71 tests** pass with Postgres+DBOS; 60 pass (11 infra skipped) with none. Durable and in-process modes share one governance path; only the backends differ.

## Phase 3 — measured multi-agent (branch `acme-phase3`)

- [x] **Fan-out + typed aggregation** (`fanout` step, `acme/kernel/aggregate.py`): run a role N times in parallel (distinct `_candidate` index) and aggregate by majority/best/first, with vote counts + agreement. Compiler validates (`E-FANOUT`).
- [x] **Independent verifier step** (`verify` step): M verifiers apply distinct lenses (`_verifier` index) over a prior artifact; passes iff approvals ≥ `verifyQuorum`, else escalates to `WAITING_FOR_HUMAN`. Compiler validates (`E-VERIFY`).
- [x] **The evaluation gate** (`acme/eval`, CLI `acme eval`): runs a single-agent baseline vs a multi-agent variant over scenarios; measures success / cost (invocations) / latency / policy-denials; **PROMOTES the variant only if it beats the baseline on success without unacceptable cost/latency/policy regressions** — encoding STRATEGY.md §5.2 and the multi-agent-failure literature.
- [x] **Triage demo** (`companies/triage-demo/`): a single-agent workflow (0.667 success) and a fan-out+verify panel (1.0 success at 6× cost) → `acme eval` returns **PROMOTE**; baseline-vs-itself returns **KEEP BASELINE** (`tests/test_phase3.py`).

**77 tests** pass with Postgres+DBOS; 66 pass (11 infra skipped) with none. Multi-agent is a promoted-on-evidence mechanism, not a default.

## Hardening (branch `acme-hardening`)

- [x] **Compiler hardening**: company-name slug validation (`E-SLUG`, safe tenant keys) + fan-out/verifier upper-bound caps (`E-FANOUT`/`E-VERIFY`, DoS guard).
- [x] **Telemetry** (`acme/telemetry.py`): pluggable Null/InMemory/OpenTelemetry; gateway emits decision events with secrets scrubbed; event log stays authoritative. Enable with `ACME_OTEL=1` + `pip install '.[otel]'`.
- [x] **Untrusted-pack guard**: `load_pack(dir, trusted=False)` refuses to execute `pack.py` (arbitrary-code / Paperclip-style RCE boundary).
- [x] **Multi-tenant isolation**: per-company event log, company-scoped action digests, verified on a shared Postgres (`tests/test_isolation.py`).
- [x] **Per-company DBOS queues**: concurrency-capped per-tenant queues so one tenant can't starve others.

**88 tests** pass with Postgres+DBOS; 75 pass (13 infra skipped) with none.

## HTTP backend (branch `acme-backend`)

- [x] **CompanyService** (`acme/server/service.py`): loads CompanyPacks from a dir; holds the shared ledger, durable DBOS engine, and shared credential/approval stores; per-company gateway/executor/runner. Task status reconstructs from the event log.
- [x] **FastAPI API** (`acme/server/app.py`) + **`acme serve`**: health, companies, start/get task, approval inbox, WebAuthn enroll + approve ceremony, eval, audit events. OpenAPI docs at `/docs`.
- [x] **Deployment**: `Dockerfile` + `docker-compose.yml` (Acme + Postgres, durable on `:8080`); `[server]` optional deps.
- [x] **Docs**: `docs/BACKEND.md` — install, run, API reference, and "where the backend lives".
- [x] Server tests (`tests/test_server.py`): full governed lifecycle over HTTP (start → enroll passkey → authenticate → authorize → SUCCEEDED) via TestClient + software authenticator; eval + audit endpoints. Live `acme serve` smoke-tested.

**93 tests** pass with Postgres+DBOS; 80 pass (13 infra skipped) with none. Acme is now a runnable backend, not just a CLI/library.

## Next

- [ ] Remaining items in docs/OPERATIONS.md "Still open" (OpenInference for model calls, row-level DB tenant enforcement, approval-TTL sweeper).
- [ ] Persist enrollment-in-progress challenges (multi-instance) + a browser UI for the approval ceremony.
- [ ] Optional: run fan-out candidates as durable DBOS steps; delegation-chain capabilities.

Run the full infra suite:
```bash
docker run -d --name acme-pg -e POSTGRES_PASSWORD=acme -e POSTGRES_DB=acme -p 5433:5432 postgres:16-alpine
DSN=postgresql://postgres:acme@127.0.0.1:5433/acme
ACME_TEST_DATABASE_URL=$DSN ACME_TEST_DBOS_URL=$DSN pytest
```

Run the Postgres conformance suite locally:
```bash
docker run -d --name acme-pg -e POSTGRES_PASSWORD=acme -e POSTGRES_DB=acme -p 5433:5432 postgres:16-alpine
ACME_TEST_DATABASE_URL=postgresql://postgres:acme@127.0.0.1:5433/acme pytest
```
