"""The default-deny capability gateway (Mandamus-Lite).

Every side effect passes through here. The gateway:
  1. resolves the action policy for an intent (unknown action -> deny),
  2. classifies the tier,
  3. auto-authorizes A0/A1 (A1 within bounded-auto envelope),
  4. routes A2/A3 to a human approval that must be cryptographically verified,
  5. denies A4 outright,
  6. mints a scoped, single-use, TTL-bound capability on authorization,
  7. emits a receipt for the decision to the ledger.

Missing policy, unknown action, ambiguous state -> deny. Never a canned allow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
from acme.spec.models import Action, Risk


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
    ):
        self._ledger = ledger
        self._actions = actions
        self._verifier = verifier or DenyByDefaultVerifier()
        self._bounds = bounds or {}
        self._calls: dict[str, int] = {}   # action_id -> count (bounded-auto)

    def decide(self, intent: ActionIntent, assertion: dict | None = None) -> GateOutcome:
        action = self._actions.get(intent.action_id)
        if action is None:
            return self._deny(intent, Tier.A4,
                              f"unknown action policy {intent.action_id!r}")
        if action.tool != intent.tool:
            return self._deny(intent, classify(action.risk),
                              f"intent tool {intent.tool!r} != policy tool {action.tool!r}")

        tier = classify(action.risk)

        if tier in DENY_TIERS:
            return self._deny(intent, tier, "prohibited action (A4)")

        if tier in AUTO_TIERS:
            return self._auto(intent, action, tier)

        if tier in APPROVAL_TIERS:
            return self._approval(intent, action, tier, assertion)

        return self._deny(intent, tier, "unclassified tier")  # unreachable

    # -- tier handlers -------------------------------------------------------

    def _auto(self, intent: ActionIntent, action: Action, tier: Tier) -> GateOutcome:
        # A1 bounded-auto: escalate to approval if it leaves the envelope.
        if tier == Tier.A1:
            b = self._bounds.get(action.id)
            count = self._calls.get(action.id, 0)
            if b is not None and not b.within(amount=intent.amount, calls_so_far=count):
                return self._approval(intent, action, Tier.A2,
                                      assertion=None,
                                      escalated="bounded-auto envelope exceeded")
            self._calls[action.id] = count + 1
        cap = self._mint(intent, tier)
        self._receipt(intent, "authorized", tier, cap.capability_id, "auto")
        return GateOutcome("auto", tier, "auto-authorized", capability=cap)

    def _approval(self, intent: ActionIntent, action: Action, tier: Tier,
                  assertion: dict | None, escalated: str = "") -> GateOutcome:
        required = TIER_REQUIRES[tier]
        appr = action.approval
        quorum = appr.quorum if appr else 1
        if tier == Tier.A3 and quorum < 2:
            return self._deny(intent, tier,
                              "A3 consequential action requires distinct-person "
                              "dual control (quorum >= 2)")
        request = {
            "intent_digest": intent.action_digest,
            "tier": tier.value,
            "required": required,
            "quorum": quorum,
            "significant": intent.canonical(),
        }
        self._emit(EventType.approval_requested, intent, request)

        if assertion is None:
            reason = "human approval required" + (f" ({escalated})" if escalated else "")
            self._receipt(intent, "require_approval", tier, None, reason)
            return GateOutcome("require_approval", tier, reason, approval_request=request)

        decision = self._verifier.verify(approval_request=request, assertion=assertion)
        self._emit(EventType.approval_resolved, intent,
                   {"approved": decision.approved, "reason": decision.reason})
        if not decision.approved:
            return self._deny(intent, tier, f"approval denied: {decision.reason}")
        cap = self._mint(intent, tier)
        self._receipt(intent, "authorized", tier, cap.capability_id, "approved")
        return GateOutcome("authorized", tier, "approved", capability=cap,
                           approval_request=request)

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
