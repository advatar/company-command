"""Model profile registry: capability profiles -> a backend.

CompanySpec names profiles (planner-high, extractor-fast, code-worker); the
deployment maps each profile to a backend. Phase 0 maps everything to the
offline-defer backend unless overridden.
"""

from __future__ import annotations

from acme.models.backends import ModelBackend, OfflineDeferBackend


class ProfileRegistry:
    def __init__(self, default: ModelBackend | None = None):
        self._default = default or OfflineDeferBackend()
        self._by_profile: dict[str, ModelBackend] = {}

    def bind(self, profile: str, backend: ModelBackend) -> "ProfileRegistry":
        self._by_profile[profile] = backend
        return self

    def backend_for(self, profile: str | None) -> ModelBackend:
        if profile is None:
            return self._default
        return self._by_profile.get(profile, self._default)
