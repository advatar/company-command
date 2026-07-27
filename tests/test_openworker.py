import json
import sys
from types import SimpleNamespace

import pytest

from comcmd.workers.api import TaskEnvelope
from comcmd.workers.openworker import OpenWorker, _websocket_runner, _websocket_url


def _env():
    return TaskEnvelope(
        company="example-studio",
        task_id="task-1",
        step_id="research",
        role="researcher",
        model_profile=None,
        inputs={"topic": "market", "_upstream": {"brief": {"region": "SE"}}},
        allowed_tools=("github.read", "slack.search"),
    )


def test_openworker_builds_read_only_prompt_and_parses_artifact(tmp_path):
    seen = {}

    def run(base_url, session_id, workspace, agent, prompt, timeout):
        seen.update(
            base_url=base_url,
            session_id=session_id,
            workspace=workspace,
            agent=agent,
            prompt=prompt,
            timeout=timeout,
        )
        return 'Finished\n{"finding": "relevant", "confidence": 0.9}'

    worker = OpenWorker(
        "http://127.0.0.1:8765",
        workspace=tmp_path,
        timeout_seconds=12,
        runner=run,
    )
    result = worker.run(_env())

    assert result.status == "ok"
    assert result.artifact == {"finding": "relevant", "confidence": 0.9}
    assert result.usage["mode"] == "plan"
    assert seen["agent"] == "cowork"
    assert seen["workspace"] == str(tmp_path.resolve())
    assert seen["timeout"] == 12
    assert "read-only" in seen["prompt"]
    assert "slack.search" in seen["prompt"]
    assert '"region": "SE"' in seen["prompt"]


def test_openworker_session_id_is_stable_for_step(tmp_path):
    ids = []

    def run(_base, session_id, _workspace, _agent, _prompt, _timeout):
        ids.append(session_id)
        return "{}"

    worker = OpenWorker(workspace=tmp_path, runner=run)
    worker.run(_env())
    worker.run(_env())
    assert ids[0] == ids[1]
    assert ids[0].startswith("comcmd-")


def test_openworker_failure_defers_without_artifact(tmp_path):
    def fail(*_args):
        raise RuntimeError("server unavailable")

    result = OpenWorker(workspace=tmp_path, runner=fail).run(_env())
    assert result.status == "deferred"
    assert result.artifact is None
    assert "server unavailable" in result.usage["reason"]


def test_websocket_url_conversion_and_validation():
    assert _websocket_url(
        "https://worker.example/base", "task 1", "/tmp/a b", "cowork"
    ) == (
        "wss://worker.example/base/ws/session/task%201"
        "?workspace=%2Ftmp%2Fa+b&agent=cowork"
    )
    with pytest.raises(ValueError):
        OpenWorker("worker.example")


def test_transport_forces_plan_mode_before_starting_turn(monkeypatch):
    class Socket:
        def __init__(self):
            self.events = iter(
                [
                    {"type": "ready", "data": {}},
                    {"type": "assistant_message", "data": {"text": '{"ok": true}'}},
                    {"type": "turn_done", "data": {}},
                ]
            )
            self.sent = []
            self.closed = False

        def recv(self):
            return json.dumps(next(self.events))

        def send(self, value):
            self.sent.append(json.loads(value))

        def close(self):
            self.closed = True

    socket = Socket()
    monkeypatch.setitem(
        sys.modules,
        "websocket",
        SimpleNamespace(create_connection=lambda _url, timeout: socket),
    )

    result = _websocket_runner(
        "http://127.0.0.1:8765", "s1", "/tmp/work", "cowork", "do work", 5
    )

    assert result == '{"ok": true}'
    assert socket.sent == [
        {"type": "set_mode", "mode": "plan"},
        {"type": "user_message", "text": "do work"},
    ]
    assert socket.closed
