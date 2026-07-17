"""Postgres-backed durable event ledger.

Same contract as `comcmd.kernel.ledger.Ledger` (append / head_seal / read /
verify_chain), but on Postgres — the durable substrate ADR-001 calls for. The
WorkflowRunner replays this log to reconstruct task state, so moving the log to
Postgres makes crash-resume durable across processes and machines, not just
across a single SQLite file.

Appends are serialized per company with a transaction-scoped advisory lock, so
concurrent writers on different processes cannot fork the hash chain:
``pg_advisory_xact_lock(hashtext(company))`` → read head → seal → insert →
commit. The seal computation is byte-for-byte identical to the SQLite ledger, so
the two backends produce the same chain for the same events (useful for
conformance).

This is the durability layer beneath the eventual DBOS workflow primitives
(queues, timers, leases); those still layer on top (see ADR-001).
"""

from __future__ import annotations

import json
import threading
from typing import Iterator

import psycopg

from comcmd.ids import canonical_json, digest
from comcmd.kernel.ledger import _GENESIS, SealedEvent
from comcmd.kernel.records import Event


class PostgresLedger:
    def __init__(self, dsn: str, *, table: str = "comcmd_events"):
        self._dsn = dsn
        self._table = table
        self._lock = threading.Lock()
        self._conn = psycopg.connect(dsn, autocommit=False)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._table} (
                    seq        BIGSERIAL PRIMARY KEY,
                    company    TEXT NOT NULL,
                    type       TEXT NOT NULL,
                    task_id    TEXT,
                    body       TEXT NOT NULL,
                    prev_seal  TEXT NOT NULL,
                    seal       TEXT NOT NULL
                )
                """
            )
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS {self._table}_company_seq "
                f"ON {self._table} (company, seq)"
            )
        self._conn.commit()

    # -- write ---------------------------------------------------------------

    def append(self, event: Event) -> SealedEvent:
        with self._lock:
            try:
                with self._conn.cursor() as cur:
                    # Serialize appends for this company across all writers.
                    cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",
                                (event.company,))
                    cur.execute(
                        f"SELECT seal FROM {self._table} WHERE company=%s "
                        f"ORDER BY seq DESC LIMIT 1",
                        (event.company,),
                    )
                    row = cur.fetchone()
                    prev_seal = row[0] if row else _GENESIS
                    body = canonical_json(event.model_dump(mode="json"))
                    seal = digest({"prev": prev_seal, "body": body})
                    cur.execute(
                        f"INSERT INTO {self._table} "
                        f"(company, type, task_id, body, prev_seal, seal) "
                        f"VALUES (%s, %s, %s, %s, %s, %s) RETURNING seq",
                        (event.company, event.type.value, event.task_id, body,
                         prev_seal, seal),
                    )
                    seq = cur.fetchone()[0]
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            return SealedEvent(seq=int(seq), company=event.company, seal=seal,
                               prev_seal=prev_seal, event=event)

    # -- read ----------------------------------------------------------------

    def head_seal(self, company: str) -> str:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                f"SELECT seal FROM {self._table} WHERE company=%s "
                f"ORDER BY seq DESC LIMIT 1", (company,))
            row = cur.fetchone()
            self._conn.rollback()  # end the implicit read txn
            return row[0] if row else _GENESIS

    def read(self, company: str) -> Iterator[SealedEvent]:
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                f"SELECT seq, company, type, task_id, body, prev_seal, seal "
                f"FROM {self._table} WHERE company=%s ORDER BY seq ASC", (company,))
            rows = cur.fetchall()
            self._conn.rollback()
        for seq, comp, _t, _task, body, prev_seal, seal in rows:
            yield SealedEvent(seq=seq, company=comp, seal=seal, prev_seal=prev_seal,
                              event=Event.model_validate(json.loads(body)))

    def verify_chain(self, company: str) -> bool:
        prev = _GENESIS
        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                f"SELECT body, prev_seal, seal FROM {self._table} "
                f"WHERE company=%s ORDER BY seq ASC", (company,))
            rows = cur.fetchall()
            self._conn.rollback()
        for body, prev_seal, seal in rows:
            if prev_seal != prev:
                return False
            if digest({"prev": prev_seal, "body": body}) != seal:
                return False
            prev = seal
        return True

    def close(self) -> None:
        self._conn.close()
