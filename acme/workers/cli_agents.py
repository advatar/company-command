"""Codex and OpenHands worker adapters.

Both implement the same `Worker` contract as the native worker, so a company can
route a step to Codex or OpenHands without changing the kernel. Each shells out
to the external agent CLI with a prompt built from the task envelope (role
instructions + step + upstream artifacts) and parses the result into a typed
`WorkerResult`. Side effects still surface as ActionIntents for the gateway;
these adapters produce artifacts, they do not perform privileged effects.

The subprocess call is injected (`runner=`) so the prompt-construction and
output-parsing logic is unit-testable without the external binary installed.
When the binary is absent, `run()` returns a `deferred` result rather than
failing — a company that lists Codex/OpenHands still degrades safely on a host
that lacks them.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Callable

from acme.workers.api import TaskEnvelope, WorkerResult

# argv -> stdout. Injected in tests; defaults to a real subprocess call.
CliRunner = Callable[[list[str], str], str]


def _subprocess_runner(argv: list[str], prompt: str) -> str:
    proc = subprocess.run(argv + [prompt], capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"{argv[0]} exited {proc.returncode}: {proc.stderr[:400]}")
    return proc.stdout


def _extract_json(text: str) -> dict | None:
    """Best-effort: parse the last balanced {...} block as JSON."""
    start = text.rfind("{")
    while start != -1:
        try:
            return json.loads(text[start:text.rindex("}") + 1])
        except Exception:
            start = text.rfind("{", 0, start)
    return None


class CliAgentWorker:
    """Base adapter for a prompt-in / text-out agent CLI."""

    name = "cli-agent"

    def __init__(self, command: list[str], *, runner: CliRunner | None = None,
                 available: bool | None = None):
        self._command = command
        self._runner = runner or _subprocess_runner
        self._available = available if available is not None \
            else bool(command) and shutil.which(command[0]) is not None

    @property
    def available(self) -> bool:
        return self._available

    def build_prompt(self, env: TaskEnvelope) -> str:
        upstream = env.inputs.get("_upstream", {})
        lines = [
            f"You are the '{env.role}' role in company '{env.company}'.",
            f"Task step: {env.step_id}.",
            f"Allowed tools: {', '.join(env.allowed_tools) or '(none)'}.",
            "Upstream artifacts (JSON):",
            json.dumps(upstream, indent=2, sort_keys=True),
            "",
            "Produce the step's output artifact as a single JSON object. "
            "Do not perform side effects; if an effect is needed, describe it.",
        ]
        return "\n".join(lines)

    def run(self, env: TaskEnvelope) -> WorkerResult:
        if not self._available:
            return WorkerResult(status="deferred", artifact=None,
                                usage={"reason": f"{self.name} not available"})
        prompt = self.build_prompt(env)
        try:
            out = self._runner(list(self._command), prompt)
        except Exception as exc:  # fail closed to a deferral, never a fake artifact
            return WorkerResult(status="error", artifact=None,
                                usage={"error": str(exc), "worker": self.name})
        artifact = _extract_json(out)
        if artifact is None:
            return WorkerResult(status="ok", artifact={"text": out.strip()},
                                usage={"worker": self.name})
        return WorkerResult(status="ok", artifact=artifact, usage={"worker": self.name})


class CodexWorker(CliAgentWorker):
    name = "codex"

    def __init__(self, *, command: list[str] | None = None,
                 runner: CliRunner | None = None, available: bool | None = None):
        super().__init__(command or ["codex", "exec"], runner=runner, available=available)


class OpenHandsWorker(CliAgentWorker):
    name = "openhands"

    def __init__(self, *, command: list[str] | None = None,
                 runner: CliRunner | None = None, available: bool | None = None):
        super().__init__(command or ["openhands", "run", "-t"], runner=runner,
                         available=available)
