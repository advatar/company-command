# ADR-001: DBOS-first durability, Temporal as a graduation path

**Status:** Accepted · 2026-07-15
**Context:** Acme Phase 0/1 · relates to Acme issue #1, `STRATEGY.md` §5.1, §11

## Context

Acme's design principle #6 is *durability before autonomy*: every long-running
task, retry, timer, human wait, and cancellation must survive a process restart.
Phase 0 satisfies this with an in-process runner over an append-only,
hash-chained event log (`acme.kernel.ledger.Ledger`, `acme.kernel.workflow`).
That is enough to prove the crash-resume property in tests, but it is not a
production durability runtime: it has no queues, no distributed leases, no timer
service, and no HA story.

We need to choose the durable workflow runtime for Phase 1.

## Decision

Adopt **DBOS on Postgres** as the first durable workflow runtime. Keep
**Temporal** as an explicit, later graduation path — not a predetermined
destination.

Rationale:

- DBOS's open-source library supplies durable execution, queues, events, and
  human-wait (send/receive) primitives directly on Postgres, which is already
  Acme's source of truth. This minimizes moving parts for Phase 1.
- Acme's kernel already isolates the durable seam behind small interfaces
  (`WorkflowRunner`, `Ledger`). DBOS implements those; the compiler, gateway,
  workers, and model layer do not change.
- Temporal is the stronger choice only when Acme needs independent services,
  multiple languages, or operational guarantees beyond a single Postgres — a
  Phase 3 concern at the earliest.

## Graduation triggers (DBOS → Temporal)

Revisit this decision (write ADR-00N) if **any** of the following is measured,
not merely anticipated:

1. Sustained workflow concurrency or throughput that a single primary Postgres
   cannot serve within latency targets.
2. A need for workers in a language without a first-class DBOS binding.
3. Operational requirements (multi-region failover, per-workflow rate isolation,
   long histories) that DBOS + Conductor cannot meet at acceptable cost.

Workflow histories are **not portable** between the engines. A migration drains
old runs to completion and starts new executions from Acme business state
(records + event log), never by importing engine history. Do **not** run DBOS
and Temporal as competing owners of the same workflow.

## Consequences

- Phase 1 replaces the in-process runner/ledger with a DBOS-backed
  implementation of the same interfaces; Phase 0 tests (crash-resume,
  idempotency, chain verification) become the conformance suite the DBOS
  implementation must also pass.
- The event log remains the authoritative audit trail regardless of engine;
  the workflow engine is an execution detail, not the system of record.
