"""A bounded, deterministic native worker.

This is not a general agent — it is a small tool loop with structured output.
For Phase 0 it runs read-only "skill" callables registered by the CompanyPack;
if a step has no registered skill it consults the model backend, which under the
offline-defer default returns a deferral (never a fabricated answer). Anything a
skill wants to *do* (side effects) it returns as ActionIntents for the gateway.
"""

from __future__ import annotations

from typing import Callable

from acme.models.profiles import ProfileRegistry
from acme.workers.api import TaskEnvelope, WorkerResult

# A skill is a pure-ish function of the envelope -> WorkerResult. Read-only by
# convention; side effects must be surfaced as intents, not performed here.
Skill = Callable[[TaskEnvelope], WorkerResult]


class NativeWorker:
    def __init__(self, skills: dict[str, Skill] | None = None,
                 profiles: ProfileRegistry | None = None):
        self._skills = skills or {}
        self._profiles = profiles or ProfileRegistry()

    def run(self, envelope: TaskEnvelope) -> WorkerResult:
        # Dispatch by step id, then fall back to the role id — so several steps
        # driven by the same role (e.g. a work step and a fan-out step) can share
        # one skill without duplicating registrations.
        skill = self._skills.get(envelope.step_id) or self._skills.get(envelope.role)
        if skill is not None:
            return skill(envelope)
        # No registered skill: consult the model profile (defers in Phase 0).
        backend = self._profiles.backend_for(envelope.model_profile)
        result = backend.complete(
            profile=envelope.model_profile or "default",
            messages=[{"role": "user", "content": f"step {envelope.step_id}"}],
        )
        if result.status == "ok":
            return WorkerResult(status="ok",
                                artifact={"text": result.text},
                                usage=result.meta)
        return WorkerResult(status="deferred", artifact=None, usage=result.meta)
