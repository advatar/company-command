"""Pending approvals + quorum accumulation.

An A2/A3 action opens a PendingApproval: a fresh random challenge bound 1:1 to
the immutable action digest, an eligibility set, a quorum, and a TTL. Approvers
present WebAuthn assertions; each verified, eligible, *distinct* principal counts
once toward quorum. When quorum is met the gateway mints the capability.

Distinct-person dual control (A3) falls out of "distinct principals ≥ quorum".
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class PendingApproval:
    action_digest: str
    challenge: bytes
    tier: str
    required: str                     # passkey | hardware_passkey
    quorum: int
    eligible: frozenset[str]
    created_at: float
    ttl_seconds: float
    approvers: set[str] = field(default_factory=set)
    used: bool = False

    def is_expired(self, now: float) -> bool:
        return now - self.created_at > self.ttl_seconds

    def satisfied(self) -> bool:
        return len(self.approvers) >= self.quorum


_TTL_UNITS = {"s": 1, "m": 60, "h": 3600}


def parse_ttl(text: str) -> float:
    text = (text or "10m").strip()
    unit = text[-1]
    if unit in _TTL_UNITS:
        return float(text[:-1]) * _TTL_UNITS[unit]
    return float(text)  # bare seconds


class ApprovalStore:
    def __init__(self, now: Callable[[], float]):
        self._now = now
        self._by_digest: dict[str, PendingApproval] = {}

    def open(self, *, action_digest: str, tier: str, required: str, quorum: int,
             eligible: frozenset[str], ttl_seconds: float) -> PendingApproval:
        existing = self._by_digest.get(action_digest)
        if existing is not None and not existing.is_expired(self._now()) and not existing.used:
            return existing
        pa = PendingApproval(
            action_digest=action_digest,
            challenge=secrets.token_bytes(32),
            tier=tier,
            required=required,
            quorum=quorum,
            eligible=eligible,
            created_at=self._now(),
            ttl_seconds=ttl_seconds,
        )
        self._by_digest[action_digest] = pa
        return pa

    def get(self, action_digest: str) -> PendingApproval | None:
        return self._by_digest.get(action_digest)

    def pending(self) -> list[PendingApproval]:
        now = self._now()
        return [p for p in self._by_digest.values()
                if not p.used and not p.is_expired(now)]

    def retire(self, action_digest: str) -> None:
        pa = self._by_digest.get(action_digest)
        if pa is not None:
            pa.used = True
