"""Idempotent executor — the only place an authorized effect actually happens.

A worker never performs a side effect; it emits an ActionIntent, the gateway
authorizes it into a Capability, and this executor runs it exactly once. The
idempotency key is the action digest, so a retry after a crash between
authorization and execution re-runs nothing: the prior execution receipt is
returned unchanged.

"Only through the gateway": ``execute`` refuses any intent whose digest does not
match a capability the gateway minted for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from comcmd.gateway.gate import Capability
from comcmd.gateway.intents import ActionIntent
from comcmd.kernel.ledger import Ledger
from comcmd.kernel.records import Event, EventType, ExecutionReceipt

ToolHandler = Callable[[ActionIntent], dict[str, Any]]


@dataclass(frozen=True)
class ExecutionOutcome:
    executed: bool
    duplicate: bool
    receipt: ExecutionReceipt
    result: dict[str, Any]


class Executor:
    def __init__(self, ledger: Ledger, handlers: dict[str, ToolHandler] | None = None):
        self._ledger = ledger
        self._handlers = handlers or {}

    def register(self, tool: str, handler: ToolHandler) -> "Executor":
        self._handlers[tool] = handler
        return self

    def execute(self, capability: Capability, intent: ActionIntent) -> ExecutionOutcome:
        # Bind: the capability must be for exactly this action.
        if capability.intent_digest != intent.action_digest:
            return self._refuse(intent, "capability does not match action digest")
        if capability.tool != intent.tool:
            return self._refuse(intent, "capability tool mismatch")

        # Idempotency: if already executed, return the prior receipt untouched.
        prior = self._prior_execution(intent)
        if prior is not None:
            return ExecutionOutcome(executed=False, duplicate=True, receipt=prior,
                                    result=prior.model_dump(mode="json"))

        handler = self._handlers.get(intent.tool)
        if handler is None:
            return self._refuse(intent, f"no handler registered for {intent.tool!r}")

        result = handler(intent)
        receipt = ExecutionReceipt(
            intent_digest=intent.action_digest,
            decision="executed",
            tier="",  # tier already recorded at authorization
            capability_id=capability.capability_id,
            reason="executed",
        )
        self._emit(intent, receipt)
        return ExecutionOutcome(executed=True, duplicate=False, receipt=receipt,
                                result=result)

    # -- helpers -------------------------------------------------------------

    def _prior_execution(self, intent: ActionIntent) -> ExecutionReceipt | None:
        for se in self._ledger.read(intent.company):
            e = se.event
            if e.type != EventType.execution_receipt:
                continue
            p = e.payload
            if p.get("decision") == "executed" and p.get("intent_digest") == intent.action_digest:
                return ExecutionReceipt.model_validate(p)
        return None

    def _refuse(self, intent: ActionIntent, reason: str) -> ExecutionOutcome:
        receipt = ExecutionReceipt(intent_digest=intent.action_digest,
                                   decision="refused", tier="", reason=reason)
        self._emit(intent, receipt)
        return ExecutionOutcome(executed=False, duplicate=False, receipt=receipt,
                                result={})

    def _emit(self, intent: ActionIntent, receipt: ExecutionReceipt) -> None:
        self._ledger.append(Event(type=EventType.execution_receipt,
                                  company=intent.company, task_id=intent.task_id,
                                  payload=receipt.model_dump(mode="json")))
