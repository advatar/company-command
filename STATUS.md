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

## Next

- [ ] Phase 2: AutoSteam as the first CompanyPack; Codex App Server + OpenHands worker adapters; open-model baseline.

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
