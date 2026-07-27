"""Read-only OpenWorker adapter.

OpenWorker supplies the local agent loop, read tools, connectors, and artifact
UX. Company Command remains authoritative for workflow state and effects. The
adapter therefore forces every session into OpenWorker's ``plan`` mode, where
writes and commands are denied, and accepts only the resulting artifact text.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

from comcmd.workers.api import TaskEnvelope, WorkerResult
from comcmd.workers.cli_agents import _extract_json


class OpenWorkerError(RuntimeError):
    pass


OpenWorkerRunner = Callable[[str, str, str, str, str, float], str]


def _websocket_url(base_url: str, session_id: str, workspace: str, agent: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https", "ws", "wss"} or not parsed.netloc:
        raise ValueError("OpenWorker URL must be an http(s) or ws(s) URL")
    scheme = {"http": "ws", "https": "wss"}.get(parsed.scheme, parsed.scheme)
    path = f"{parsed.path.rstrip('/')}/ws/session/{quote(session_id, safe='')}"
    query = urlencode({"workspace": workspace, "agent": agent})
    return urlunsplit((scheme, parsed.netloc, path, query, ""))


def _websocket_runner(
    base_url: str,
    session_id: str,
    workspace: str,
    agent: str,
    prompt: str,
    timeout: float,
) -> str:
    try:
        import websocket
    except ImportError as exc:
        raise OpenWorkerError(
            "OpenWorker support is not installed; install comcmd[openworker]"
        ) from exc

    ws = websocket.create_connection(
        _websocket_url(base_url, session_id, workspace, agent),
        timeout=timeout,
    )
    messages: list[str] = []
    try:
        ready = json.loads(ws.recv())
        if ready.get("type") == "error":
            raise OpenWorkerError(str(ready.get("data", {}).get("error", "startup failed")))
        if ready.get("type") != "ready":
            raise OpenWorkerError(f"expected ready event, got {ready.get('type')!r}")

        # Acme never delegates effect authorization to OpenWorker's session
        # approval system.
        ws.send(json.dumps({"type": "set_mode", "mode": "plan"}))
        ws.send(json.dumps({"type": "user_message", "text": prompt}))
        while True:
            event = json.loads(ws.recv())
            kind = event.get("type")
            data = event.get("data") or {}
            if kind == "assistant_message":
                text = str(data.get("text") or data.get("content") or "").strip()
                if text:
                    messages.append(text)
            elif kind in {
                "permission_required",
                "directory_requested",
                "plan_proposed",
                "question_requested",
            }:
                raise OpenWorkerError(
                    f"OpenWorker requested interaction in read-only worker mode: {kind}"
                )
            elif kind == "error":
                raise OpenWorkerError(str(data.get("error") or data.get("message") or data))
            elif kind == "turn_done":
                break
        if not messages:
            raise OpenWorkerError("OpenWorker completed without an assistant artifact")
        return messages[-1]
    finally:
        ws.close()


class OpenWorker:
    """Use a running local OpenWorker server as a read-only Acme worker."""

    name = "openworker"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8765",
        *,
        workspace: str | Path = ".",
        agent: str = "cowork",
        timeout_seconds: float = 600,
        runner: OpenWorkerRunner | None = None,
    ):
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.base_url = base_url.rstrip("/")
        self.workspace = str(Path(workspace).expanduser().resolve())
        self.agent = agent
        self.timeout_seconds = timeout_seconds
        self._runner = runner or _websocket_runner
        _websocket_url(self.base_url, "validation", self.workspace, self.agent)

    def build_prompt(self, env: TaskEnvelope) -> str:
        return "\n".join(
            [
                f"You are the '{env.role}' role in company '{env.company}'.",
                f"Complete task {env.task_id}, step {env.step_id}.",
                "You are operating as a read-only research and artifact worker.",
                "Do not write files, run commands, send messages, change external systems, "
                "or request approval. Describe any needed effect in the artifact for Company "
                "Command to authorize separately.",
                f"Available read-tool scope: {', '.join(env.allowed_tools) or '(none)'}.",
                "Task inputs and upstream artifacts (JSON):",
                json.dumps(env.inputs, indent=2, sort_keys=True, default=str),
                "",
                "Return the completed artifact as a single JSON object.",
            ]
        )

    def run(self, env: TaskEnvelope) -> WorkerResult:
        identity = f"{env.company}\0{env.task_id}\0{env.step_id}".encode()
        session_id = "comcmd-" + hashlib.sha256(identity).hexdigest()[:20]
        try:
            output = self._runner(
                self.base_url,
                session_id,
                self.workspace,
                self.agent,
                self.build_prompt(env),
                self.timeout_seconds,
            )
        except Exception as exc:
            return WorkerResult(
                status="deferred",
                usage={"worker": self.name, "reason": str(exc)},
            )
        artifact = _extract_json(output)
        if artifact is None:
            artifact = {"text": output.strip()}
        return WorkerResult(
            status="ok",
            artifact=artifact,
            usage={"worker": self.name, "session_id": session_id, "mode": "plan"},
        )
