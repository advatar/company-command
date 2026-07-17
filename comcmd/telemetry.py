"""Operational telemetry — a projection, never the audit trail.

Gateway decisions, step execution, and model calls emit telemetry so operators
can observe the system. The authoritative record is always the hash-chained
event log; telemetry is lossy and best-effort. It must never carry secrets —
no challenges, assertions, capabilities, private keys, or raw model prompts.

Pluggable: `NullTelemetry` (default, zero cost), `InMemoryTelemetry` (tests /
introspection), and an optional OpenTelemetry backend when `opentelemetry-api`
is installed and `COMCMD_OTEL=1`.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator, Protocol


class Telemetry(Protocol):
    def event(self, name: str, **attrs: Any) -> None: ...
    def span(self, name: str, **attrs: Any): ...


class NullTelemetry:
    def event(self, name: str, **attrs: Any) -> None:
        pass

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[None]:
        yield


@dataclass
class InMemoryTelemetry:
    events: list[tuple[str, dict]] = field(default_factory=list)
    spans: list[str] = field(default_factory=list)

    def event(self, name: str, **attrs: Any) -> None:
        self.events.append((name, attrs))

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[None]:
        self.spans.append(name)
        yield

    def events_named(self, name: str) -> list[dict]:
        return [a for n, a in self.events if n == name]


class OTelTelemetry:
    """OpenTelemetry backend. Only constructed when the package is present."""

    def __init__(self, tracer_name: str = "comcmd"):
        from opentelemetry import trace  # gated import
        self._tracer = trace.get_tracer(tracer_name)

    def event(self, name: str, **attrs: Any) -> None:
        from opentelemetry import trace
        span = trace.get_current_span()
        span.add_event(name, attributes=_scrub(attrs))

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[None]:
        with self._tracer.start_as_current_span(name, attributes=_scrub(attrs)):
            yield


# Keys that must never be exported even if a caller passes them by mistake.
_FORBIDDEN = {"challenge", "assertion", "signature", "private_key", "capability",
              "secret", "password", "token", "prompt"}


def _scrub(attrs: dict) -> dict:
    return {k: v for k, v in attrs.items() if k.lower() not in _FORBIDDEN}


_default: Telemetry = NullTelemetry()


def get_telemetry() -> Telemetry:
    return _default


def set_telemetry(t: Telemetry) -> None:
    global _default
    _default = t


def configure_from_env() -> Telemetry:
    if os.environ.get("COMCMD_OTEL") == "1":
        try:
            set_telemetry(OTelTelemetry())
        except Exception:
            pass  # fall back to Null if OTel isn't importable
    return _default
