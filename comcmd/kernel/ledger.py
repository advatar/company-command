"""Append-only, per-company hash-chained event ledger.

This is the authoritative audit trail and the substrate for crash-resume: the
workflow runner replays it to reconstruct task state. Each event is sealed with
``seal = sha256(prev_seal || canonical(event))`` so truncation or rewrite of any
prior event is detectable by ``verify_chain``.

Backed by SQLite (durable across process restarts) or an in-memory database for
tests. This is the Phase-0 stand-in for the DBOS/Postgres event store; the
``Ledger`` surface is what the DBOS implementation will provide in Phase 1.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from comcmd.ids import canonical_json, digest
from comcmd.kernel.records import Event

_GENESIS = "sha256:" + "0" * 64


@dataclass(frozen=True)
class SealedEvent:
    seq: int
    company: str
    seal: str
    prev_seal: str
    event: Event


class Ledger:
    def __init__(self, path: str | Path = ":memory:"):
        self._path = str(path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                seq        INTEGER PRIMARY KEY AUTOINCREMENT,
                company    TEXT NOT NULL,
                type       TEXT NOT NULL,
                task_id    TEXT,
                body       TEXT NOT NULL,   -- canonical json of the Event
                prev_seal  TEXT NOT NULL,
                seal       TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    # -- write ---------------------------------------------------------------

    def append(self, event: Event) -> SealedEvent:
        """Atomically seal and append one event to its company's chain."""
        with self._lock:
            prev_seal = self._head_seal(event.company)
            body = canonical_json(event.model_dump(mode="json"))
            seal = digest({"prev": prev_seal, "body": body})
            cur = self._conn.execute(
                "INSERT INTO events (company, type, task_id, body, prev_seal, seal) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (event.company, event.type.value, event.task_id, body, prev_seal, seal),
            )
            self._conn.commit()
            return SealedEvent(
                seq=int(cur.lastrowid),
                company=event.company,
                seal=seal,
                prev_seal=prev_seal,
                event=event,
            )

    # -- read ----------------------------------------------------------------

    def _head_seal(self, company: str) -> str:
        row = self._conn.execute(
            "SELECT seal FROM events WHERE company=? ORDER BY seq DESC LIMIT 1",
            (company,),
        ).fetchone()
        return row[0] if row else _GENESIS

    def head_seal(self, company: str) -> str:
        with self._lock:
            return self._head_seal(company)

    def read(self, company: str) -> Iterator[SealedEvent]:
        rows = self._conn.execute(
            "SELECT seq, company, type, task_id, body, prev_seal, seal "
            "FROM events WHERE company=? ORDER BY seq ASC",
            (company,),
        ).fetchall()
        for seq, comp, _type, _task, body, prev_seal, seal in rows:
            import json

            yield SealedEvent(
                seq=seq,
                company=comp,
                seal=seal,
                prev_seal=prev_seal,
                event=Event.model_validate(json.loads(body)),
            )

    def verify_chain(self, company: str) -> bool:
        """Recompute the chain; return False on any tamper/truncation/reorder."""
        prev = _GENESIS
        rows = self._conn.execute(
            "SELECT body, prev_seal, seal FROM events WHERE company=? ORDER BY seq ASC",
            (company,),
        ).fetchall()
        for body, prev_seal, seal in rows:
            if prev_seal != prev:
                return False
            expect = digest({"prev": prev_seal, "body": body})
            if expect != seal:
                return False
            prev = seal
        return True

    def close(self) -> None:
        self._conn.close()
