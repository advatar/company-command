"""The default-deny capability gateway (Mandamus-Lite).

Every side effect passes through here. The gateway:
  1. resolves the action policy for an intent (unknown action -> deny),
  2. classifies the tier,
  3. auto-authorizes A0/A1 (A1 within a bounded-auto envelope),
  4. opens a human approval for A2/A3 and accumulates distinct-approver quorum,
  5. denies A4 outright,
  6. mints a scoped, single-use, TTL-bound capability on authorization,
  7. emits a receipt for every decision to the ledger.

Missing policy, unknown action, ambiguous state -> deny. Never a canned allow.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from acme.gateway.approvals import ApprovalStore, parse_ttl
from acme.gateway.intents import ActionIntent
from acme.gateway.policy import (
    APPROVAL_TIERS,
    AUTO_TIERS,
    Bounds,
    DENY_TIERS,
    TIER_REQUIRES,
    Tier,
    classify,
)
from acme.gateway.verifier import ApprovalVerifier, DenyByDefaultVerifier
from acme.ids import content_id
from acme.kernel.ledger import Ledger
from acme.kernel.records import Event, EventType, ExecutionReceipt
from acme.spec.models import Action


@dataclass(frozen=True)
class Capability:
    capability_id: str
    intent_digest: str
    tool: str
    scope: dict[str, Any]
    ttl: str
    single_use: bool = True


@dataclass(frozen=True)
class GateOutcome:
    decision: str            # "auto" | "require_approval" | "authorized" | "deny"
    tier: Tier
    reason: str
    capability: Capability | None = None
    approval_request: dict | None = None


class Gateway:
    def __init__(
        self,
        ledger: Ledger,
        actions: dict[str, Action],
        verifier: ApprovalVerifier | None = None,
        bounds: dict[str, Bounds] | None = None,
        now: Callable[[], float] | None = None,
    ):
        self._ledger = ledger
        self._actions = actions
        self._verifier = verifier or DenyByDefaultVerifier()
        self._bounds = bounds or {}
        self._now = now or time.time
        self._approvals = ApprovalStore(self._now)
        self._calls: dict[str, int] = {}   # action_id -> count (bounded-auto)

    # -- public API ----------------------------------------------------------

    def decide(self, intent: ActionIntent, assertion: dict | None = None) -> GateOutcome:
        """Classify and, for auto tiers, authorize. For A2/A3, open an approval.

        If ``assertion`` is supplied it is submitted immediately (single-shot
        convenience for a quorum-1 action or a test).
        """
        action = self._actions.get(intent.action_id)
        if action is None:
            return self._deny(intent, Tier.A4,
                              f"unknown action policy {intent.action_id!r}")
        if action.tool != intent.tool:
            return self._deny(intent, classify(action.risk),
                              f"intent tool {intent.tool!r} != policy tool "
                              f"{action.tool!r}")

        tier = classify(action.risk)

        if tier in DENY_TIERS:
            return self._deny(intent, tier, "prohibited action (A4)")
        if tier in AUTO_TIERS:
            return self._auto(intent, action, tier)
        if tier in APPROVAL_TIERS:
            outcome = self._open_approval(intent, action, tier)
            if assertion is not None and outcome.decision == "require_approval":
                return self.submit_approval(intent, assertion)
            return outcome
        return self._deny(intent, tier, "unclassified tier")  # unreachable

    def submit_approval(self, intent: ActionIntent, assertion: dict) -> GateOutcome:
        """Verify one approver's assertion; authorize once quorum is reached."""
        action = self._actions.get(intent.action_id)
        if action is None:
            return self._deny(intent, Tier.A4, "unknown action policy")
        tier = classify(action.risk)
        if tier not in APPROVAL_TIERS:
            return self._deny(intent, tier, "action does not use approval")

        pa = self._approvals.get(intent.action_digest)
        if pa is None:
            # No open approval — open one now, then continue to verify.
            open_outcome = self._open_approval(intent, action, tier)
            if open_outcome.decision == "deny":
                return open_outcome
            pa = self._approvals.get(intent.action_digest)
        if pa is None or pa.used:
            return self._deny(intent, tier, "no open approval for this action")
        if pa.is_expired(self._now()):
            self._approvals.retire(intent.action_digest)
            return self._deny(intent, tier, "approval expired")

        request = self._request_view(intent, pa)
        decision = self._verifier.verify(approval_request=request, assertion=assertion)
        self._emit(EventType.approval_resolved, intent,
                   {"approved": decision.approved, "principal": decision.principal,
                    "reason": decision.reason})
        if not decision.approved:
            return GateOutcome("require_approval", tier,
                               f"approval attempt rejected: {decision.reason}",
                               approval_request=self._public_request(pa))

        principal = decision.principal
        if principal is None or principal not in pa.eligible:
            return GateOutcome("require_approval", tier,
                               f"approver {principal!r} is not eligible",
                               approval_request=self._public_request(pa))
        if principal in pa.approvers:
            return GateOutcome("require_approval", tier,
                               f"{principal} already approved; "
                               f"{pa.quorum - len(pa.approvers)} more required",
                               approval_request=self._public_request(pa))

        pa.approvers.add(principal)
        if not pa.satisfied():
            remaining = pa.quorum - len(pa.approvers)
            return GateOutcome("require_approval", tier,
                               f"{remaining} more distinct approver(s) required",
                               approval_request=self._public_request(pa))

        # Quorum met — authorize exactly once.
        self._approvals.retire(intent.action_digest)
        cap = self._mint(intent, tier)
        self._receipt(intent, "authorized", tier, cap.capability_id,
                      f"approved by {sorted(pa.approvers)}")
        return GateOutcome("authorized", tier, "approved", capability=cap,
                           approval_request=self._public_request(pa))

    def pending_approvals(self) -> list[dict]:
        return [self._public_request(pa) for pa in self._approvals.pending()]

    def challenge_for(self, action_digest: str) -> bytes | None:
        pa = self._approvals.get(action_digest)
        return pa.challenge if pa else None

    # -- tier handlers -------------------------------------------------------

    def _auto(self, intent: ActionIntent, action: Action, tier: Tier) -> GateOutcome:
        if tier == Tier.A1:
            b = self._bounds.get(action.id)
            count = self._calls.get(action.id, 0)
            if b is not None and not b.within(amount=intent.amount, calls_so_far=count):
                return self._open_approval(intent, action, Tier.A2,
                                           escalated="bounded-auto envelope exceeded")
            self._calls[action.id] = count + 1
        cap = self._mint(intent, tier)
        self._receipt(intent, "authorized", tier, cap.capability_id, "auto")
        return GateOutcome("auto", tier, "auto-authorized", capability=cap)

    def _open_approval(self, intent: ActionIntent, action: Action, tier: Tier,
                       escalated: str = "") -> GateOutcome:
        required = TIER_REQUIRES[tier]
        appr = action.approval
        quorum = appr.quorum if appr else 1
        eligible = frozenset(appr.roles if appr else [])
        if tier == Tier.A3 and quorum < 2:
            return self._deny(intent, tier,
                              "A3 consequential action requires distinct-person "
                              "dual control (quorum >= 2)")
        if not eligible:
            return self._deny(intent, tier, "no eligible approver configured")
        ttl = parse_ttl(appr.ttl if appr else "10m")
        pa = self._approvals.open(action_digest=intent.action_digest, tier=tier.value,
                                  required=required, quorum=quorum, eligible=eligible,
                                  ttl_seconds=ttl)
        self._emit(EventType.approval_requested, intent, self._public_request(pa))
        reason = "human approval required" + (f" ({escalated})" if escalated else "")
        self._receipt(intent, "require_approval", tier, None, reason)
        return GateOutcome("require_approval", tier, reason,
                           approval_request=self._public_request(pa))

    def _deny(self, intent: ActionIntent, tier: Tier, reason: str) -> GateOutcome:
        self._receipt(intent, "deny", tier, None, reason)
        return GateOutcome("deny", tier, reason)

    # -- helpers -------------------------------------------------------------

    def _mint(self, intent: ActionIntent, tier: Tier) -> Capability:
        appr = self._actions[intent.action_id].approval
        ttl = appr.ttl if appr else "0s"
        scope = {"tool": intent.tool, "target": intent.target, "task_id": intent.task_id}
        cap_id = content_id("cap", {"digest": intent.action_digest, "tier": tier.value})
        return Capability(cap_id, intent.action_digest, intent.tool, scope, ttl)

    def _request_view(self, intent: ActionIntent, pa) -> dict:
        """Internal request incl. the raw challenge for the verifier."""
        return {
            "intent_digest": intent.action_digest,
            "tier": pa.tier,
            "required": pa.required,
            "quorum": pa.quorum,
            "significant": intent.canonical(),
            "_challenge": pa.challenge,
        }

    def _public_request(self, pa) -> dict:
        """Operator-facing view (base64url challenge, no secrets)."""
        import base64
        return {
            "intent_digest": pa.action_digest,
            "tier": pa.tier,
            "required": pa.required,
            "quorum": pa.quorum,
            "approvers": sorted(pa.approvers),
            "eligible": sorted(pa.eligible),
            "challenge_b64": base64.urlsafe_b64encode(pa.challenge).decode().rstrip("="),
        }

    def _receipt(self, intent: ActionIntent, decision: str, tier: Tier,
                 cap_id: str | None, reason: str) -> None:
        receipt = ExecutionReceipt(
            intent_digest=intent.action_digest,
            decision=decision,
            tier=tier.value,
            capability_id=cap_id,
            reason=reason,
        )
        self._emit(EventType.execution_receipt, intent, receipt.model_dump(mode="json"))

    def _emit(self, etype: EventType, intent: ActionIntent, payload: dict) -> None:
        self._ledger.append(Event(
            type=etype,
            company=intent.company,
            task_id=intent.task_id,
            payload=payload,
        ))
