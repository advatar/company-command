"""Durable-runtime seam.

Phase 0/1 run on the in-process `WorkflowRunner` over the hash-chained event
ledger, which is enough to prove crash-resume and idempotency in tests. The
*production* durability upgrade (ADR-001) is DBOS on Postgres.

This module defines the seam and an availability check so the upgrade is honest:
Acme does not pretend to be Postgres-durable when it is running on SQLite. A
DBOS-backed implementation of `WorkflowRunner`'s interface is a Phase 1
deliverable that requires a running Postgres and the optional `dbos` dependency;
until then `require_durable_backend()` fails loudly rather than silently
degrading.
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
        "DBOS-backed WorkflowRunner is the Phase 1 durability deliverable and is "
        "not wired yet. The in-process runner is the current default."
    )
