"""Worker API — the one narrow lifecycle every worker implements.

Codex App Server and OpenHands become adapters behind this same contract in
Phase 2. A worker reads allowed inputs and emits typed artifacts, questions, or
ActionIntents. It never writes control-plane state and never commits its own
consequential action — only the gateway can.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from acme.gateway.intents import ActionIntent


@dataclass(frozen=True)
class TaskEnvelope:
    company: str
    task_id: str
    step_id: str
    role: str
    model_profile: str | None
    inputs: dict[str, Any] = field(default_factory=dict)
    allowed_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkerResult:
    status: str                              # "ok" | "deferred" | "error"
    artifact: dict[str, Any] | None = None   # typed output
    intents: list[ActionIntent] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)


class Worker(Protocol):
    def run(self, envelope: TaskEnvelope) -> WorkerResult: ...
