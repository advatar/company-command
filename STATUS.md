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
- [x] **DBOS/Postgres durability seam** (`acme/kernel/durable.py`), honestly infra-gated: `require_durable_backend` fails loudly rather than silently degrading. Concrete DBOS runner remains the one open Phase 1 item.

**Phase 1 exit gate met (approval half):** no worker performs an external write except through the gateway, and every approved write binds to an immutable action revision (`tests/test_approval_e2e.py`). Remaining: swap the in-process runner/ledger for DBOS on Postgres (Phase 0/1 tests become its conformance suite).

## Next

- [ ] Concrete DBOS-on-Postgres `WorkflowRunner` behind the `durable.py` seam (requires Postgres + `pip install '.[durable]'`).
- [ ] Phase 2: AutoSteam as the first CompanyPack; Codex App Server + OpenHands worker adapters; open-model baseline.
