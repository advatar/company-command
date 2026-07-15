"""Durable-runtime seam.

The durability upgrade (ADR-001) lands in two layers:

  1. Durable event log — DONE. `acme.kernel.ledger_pg.PostgresLedger` puts the
     hash-chained event log on Postgres with per-company advisory-locked atomic
     appends, so crash-resume is durable across processes and machines (proven
     by the conformance tests in tests/test_ledger_pg.py, which include the
     Phase 0 crash-resume gate running over Postgres). Select it via
     `acme.kernel.make_ledger("postgresql://...")`.
  2. Durable workflow *primitives* — queues, timers, leases, HA — via DBOS on
     Postgres. Not wired yet; `require_durable_backend()` below fails loudly
     rather than letting a caller assume they exist.

The point of the guard is honesty: Acme does not pretend to have DBOS's
scheduling guarantees just because its event log is on Postgres.
"""

from __future__ import annotations

from typing import Protocol


class DurableBackend(Protocol):
    """What a production durable backend must provide (DBOS implements this).

    The in-process runner satisfies the same observable contract (start / resume
    / approve_step over an append-only log); DBOS adds real queues, timers,
    leases, and HA on Postgres.
    """

    def start(self, workflow_id: str, inputs: dict | None = None): ...
    def resume(self, task_id: str, workflow_id: str, inputs: dict | None = None): ...


def dbos_available() -> bool:
    try:
        import dbos  # noqa: F401
    except Exception:
        return False
    return True


def require_durable_backend(dsn: str | None) -> None:
    """Guard for enabling Postgres durability. Fails closed, never silently.

    Raises with actionable guidance if the optional dependency or a Postgres DSN
    is missing. Phase 1 wires the concrete DBOS runner behind this check; see
    docs/adr/ADR-001-dbos-first-durability.md.
    """
    if not dbos_available():
        raise RuntimeError(
            "Postgres durability requested but the 'dbos' package is not "
            "installed. Install with: pip install '.[durable]'. Until then Acme "
            "runs on the in-process SQLite-backed runner (crash-resume proven in "
            "tests, but not production-HA)."
        )
    if not dsn:
        raise RuntimeError(
            "Postgres durability requested but no DSN was provided "
            "(set ACME_DATABASE_URL). See ADR-001."
        )
    raise NotImplementedError(
        "DBOS-backed workflow primitives (queues/timers/leases/HA) are not wired "
        "yet. The durable event log IS available now via "
        "make_ledger('postgresql://...') — use that for cross-process durability; "
        "the in-process runner drives it."
    )
