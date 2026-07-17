"""Postgres-backed credential and approval stores.

For production / HA, enrollment and pending approvals must outlive a single
process so an approval opened on one node can be completed on another. These
implement the same interfaces as the in-memory `CredentialStore` /
`ApprovalStore`, so the gateway and verifier are unchanged — only the store
construction differs.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

import psycopg

from comcmd.gateway.approvals import PendingApproval
from comcmd.gateway.enrollment import EnrolledCredential


class PgCredentialStore:
    def __init__(self, dsn: str, *, table: str = "comcmd_credentials"):
        self._table = table
        self._lock = threading.Lock()
        self._conn = psycopg.connect(dsn, autocommit=True)
        self._conn.execute(
            f"""CREATE TABLE IF NOT EXISTS {table} (
                credential_id BYTEA PRIMARY KEY,
                principal     TEXT NOT NULL,
                public_key    BYTEA NOT NULL,
                sign_count    BIGINT NOT NULL DEFAULT 0
            )""")

    def enroll_verified(self, principal, *, credential_id, public_key,
                        sign_count=0) -> EnrolledCredential:
        with self._lock:
            self._conn.execute(
                f"INSERT INTO {self._table} (credential_id, principal, public_key, "
                f"sign_count) VALUES (%s,%s,%s,%s) ON CONFLICT (credential_id) "
                f"DO UPDATE SET principal=EXCLUDED.principal, "
                f"public_key=EXCLUDED.public_key, sign_count=EXCLUDED.sign_count",
                (credential_id, principal, public_key, sign_count))
        return EnrolledCredential(principal, credential_id, public_key, sign_count)

    def enroll_registration(self, principal, *, credential, expected_challenge,
                            rp_id, origin) -> EnrolledCredential:
        import webauthn
        vr = webauthn.verify_registration_response(
            credential=credential, expected_challenge=expected_challenge,
            expected_rp_id=rp_id, expected_origin=origin)
        return self.enroll_verified(principal, credential_id=vr.credential_id,
                                    public_key=vr.credential_public_key,
                                    sign_count=vr.sign_count)

    def get(self, credential_id: bytes) -> EnrolledCredential | None:
        row = self._conn.execute(
            f"SELECT principal, public_key, sign_count FROM {self._table} "
            f"WHERE credential_id=%s", (credential_id,)).fetchone()
        if row is None:
            return None
        return EnrolledCredential(row[0], bytes(credential_id), bytes(row[1]), row[2])

    def principals(self) -> list[str]:
        rows = self._conn.execute(
            f"SELECT DISTINCT principal FROM {self._table}").fetchall()
        return [r[0] for r in rows]

    def update_sign_count(self, credential_id: bytes, new_count: int) -> None:
        with self._lock:
            self._conn.execute(
                f"UPDATE {self._table} SET sign_count=%s WHERE credential_id=%s",
                (new_count, credential_id))

    def close(self) -> None:
        self._conn.close()


class PgApprovalStore:
    def __init__(self, dsn: str, *, now: Callable[[], float] | None = None,
                 table: str = "comcmd_approvals"):
        self._table = table
        self._now = now or time.time
        self._lock = threading.Lock()
        self._conn = psycopg.connect(dsn, autocommit=True)
        self._conn.execute(
            f"""CREATE TABLE IF NOT EXISTS {table} (
                action_digest TEXT PRIMARY KEY,
                challenge     BYTEA NOT NULL,
                tier          TEXT NOT NULL,
                required      TEXT NOT NULL,
                quorum        INT NOT NULL,
                eligible      TEXT[] NOT NULL,
                created_at    DOUBLE PRECISION NOT NULL,
                ttl_seconds   DOUBLE PRECISION NOT NULL,
                approvers     TEXT[] NOT NULL DEFAULT '{{}}',
                used          BOOLEAN NOT NULL DEFAULT FALSE
            )""")

    def _row_to_pa(self, row) -> PendingApproval:
        (digest, challenge, tier, required, quorum, eligible, created_at,
         ttl, approvers, used) = row
        pa = PendingApproval(action_digest=digest, challenge=bytes(challenge),
                             tier=tier, required=required, quorum=quorum,
                             eligible=frozenset(eligible), created_at=created_at,
                             ttl_seconds=ttl, approvers=set(approvers), used=used)
        return pa

    def open(self, *, action_digest, tier, required, quorum, eligible,
             ttl_seconds) -> PendingApproval:
        with self._lock:
            existing = self.get(action_digest)
            if existing is not None and not existing.used \
                    and not existing.is_expired(self._now()):
                return existing
            import secrets
            challenge = secrets.token_bytes(32)
            self._conn.execute(
                f"INSERT INTO {self._table} (action_digest, challenge, tier, "
                f"required, quorum, eligible, created_at, ttl_seconds, approvers, "
                f"used) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'{{}}',FALSE) "
                f"ON CONFLICT (action_digest) DO UPDATE SET challenge=EXCLUDED.challenge, "
                f"created_at=EXCLUDED.created_at, ttl_seconds=EXCLUDED.ttl_seconds, "
                f"approvers='{{}}', used=FALSE",
                (action_digest, challenge, tier, required, quorum, list(eligible),
                 self._now(), ttl_seconds))
            return self.get(action_digest)

    def get(self, action_digest: str) -> PendingApproval | None:
        row = self._conn.execute(
            f"SELECT action_digest, challenge, tier, required, quorum, eligible, "
            f"created_at, ttl_seconds, approvers, used FROM {self._table} "
            f"WHERE action_digest=%s", (action_digest,)).fetchone()
        return self._row_to_pa(row) if row else None

    def add_approver(self, action_digest: str, principal: str) -> PendingApproval | None:
        with self._lock:
            self._conn.execute(
                f"UPDATE {self._table} SET approvers = "
                f"(SELECT ARRAY(SELECT DISTINCT unnest(approvers || %s::text))) "
                f"WHERE action_digest=%s", ([principal], action_digest))
        return self.get(action_digest)

    def pending(self) -> list[PendingApproval]:
        rows = self._conn.execute(
            f"SELECT action_digest, challenge, tier, required, quorum, eligible, "
            f"created_at, ttl_seconds, approvers, used FROM {self._table} "
            f"WHERE used=FALSE").fetchall()
        now = self._now()
        return [pa for pa in map(self._row_to_pa, rows) if not pa.is_expired(now)]

    def retire(self, action_digest: str) -> None:
        with self._lock:
            self._conn.execute(
                f"UPDATE {self._table} SET used=TRUE WHERE action_digest=%s",
                (action_digest,))

    def close(self) -> None:
        self._conn.close()
