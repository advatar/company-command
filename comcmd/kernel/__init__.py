"""Kernel: durable records, event ledger, workflow runner, executor.

`make_ledger` selects a ledger backend from a URL so the same code runs on the
in-process SQLite ledger (default) or the Postgres durable ledger.
"""

from __future__ import annotations


def make_ledger(url: str | None = None):
    """Return a ledger for `url`.

    - None / ":memory:" / a filesystem path -> SQLite `Ledger`
    - "postgres://..." / "postgresql://..."  -> `PostgresLedger`
    """
    if url and url.startswith(("postgres://", "postgresql://")):
        from comcmd.kernel.ledger_pg import PostgresLedger
        return PostgresLedger(url)
    from comcmd.kernel.ledger import Ledger
    return Ledger(url or ":memory:")
