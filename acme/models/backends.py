"""Model backends behind one profile-based boundary (provider neutrality).

Phase 0 default is OfflineDeferBackend: it never calls the network and always
returns a `deferred` result, so the kernel, compiler, gateway, and workflow can
be built and tested with zero model dependency. OpenAICompatBackend targets any
OpenAI-compatible endpoint (vLLM / SGLang / llama.cpp / hosted) but is only used
when a company profile is explicitly wired to a live URL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ModelResult:
    status: str                     # "ok" | "deferred" | "error"
    text: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


class ModelBackend(Protocol):
    def complete(self, *, profile: str, messages: list[dict],
                 tools: list[dict] | None = None) -> ModelResult: ...


class OfflineDeferBackend:
    """No network. Deterministic. Always defers model reasoning to a human/no-op."""

    def complete(self, *, profile: str, messages: list[dict],
                 tools: list[dict] | None = None) -> ModelResult:
        return ModelResult(
            status="deferred",
            text="",
            meta={"profile": profile, "reason": "offline-defer backend (Phase 0)"},
        )


class OpenAICompatBackend:
    """Thin client for an OpenAI-compatible /chat/completions endpoint.

    Deliberately lazy about the network: importing this module must not require
    connectivity. The request is only issued when `complete` is called.
    """

    def __init__(self, base_url: str, api_key: str | None = None,
                 model_map: dict[str, str] | None = None, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_map = model_map or {}
        self.timeout = timeout

    def complete(self, *, profile: str, messages: list[dict],
                 tools: list[dict] | None = None) -> ModelResult:
        import json
        import urllib.request

        model = self.model_map.get(profile, profile)
        body = {"model": model, "messages": messages}
        if tools:
            body["tools"] = tools
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # fail closed to a deferral, never a fake answer
            return ModelResult(status="error", meta={"error": str(exc), "profile": profile})
        choice = (data.get("choices") or [{}])[0].get("message", {})
        return ModelResult(
            status="ok",
            text=choice.get("content") or "",
            tool_calls=choice.get("tool_calls") or [],
            meta={"profile": profile, "model": model},
        )
