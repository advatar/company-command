"""Approval verification seam.

In Phase 0 this is deliberately DenyByDefault: an A2+ action that requires human
approval cannot be authorized until Phase 1 wires a real WebAuthn
ApprovalVerifier. Fail-closed is the point — a stubbed verifier must never
approve. A test-only AlwaysApprove verifier exists for exercising the
happy-path plumbing, and must never be the default.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Decision:
    approved: bool
    reason: str = ""


class ApprovalVerifier(Protocol):
    def verify(self, *, approval_request: dict, assertion: dict | None) -> Decision: ...


class DenyByDefaultVerifier:
    """The safe default. No assertion path exists yet, so everything denies."""

    def verify(self, *, approval_request: dict, assertion: dict | None) -> Decision:
        return Decision(False, "no approval verifier configured (Phase 0 deny-by-default)")


class AlwaysApproveVerifier:
    """TEST ONLY. Simulates a completed approval ceremony. Never use in prod."""

    def verify(self, *, approval_request: dict, assertion: dict | None) -> Decision:
        return Decision(True, "test verifier")
