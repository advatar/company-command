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

## Next — Phase 1 (governed effects + human approval)

- [ ] Replace in-process runner/ledger with DBOS on Postgres (same interfaces; Phase 0 tests become the conformance suite).
- [ ] Real WebAuthn `ApprovalVerifier` bound one-to-one to the immutable action record; commit-time revalidation; operator approval inbox.
- [ ] Idempotent executor + task-scoped credentials/sandbox profiles.
