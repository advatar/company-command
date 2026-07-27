import json
import subprocess
from pathlib import Path

from comcmd.workers.api import TaskEnvelope
from comcmd.workers.loop import LoopPolicy, LoopWorker


def _git(*args: str, cwd: Path) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )
    return proc.stdout


def _source_repository(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    _git("init", "-q", cwd=source)
    _git("config", "user.email", "loop-worker@example.invalid", cwd=source)
    _git("config", "user.name", "Loop Worker Test", cwd=source)
    (source / "app.txt").write_text("before\n")
    _git("add", "app.txt", cwd=source)
    _git("commit", "-q", "-m", "initial", cwd=source)
    return source


def _envelope() -> TaskEnvelope:
    return TaskEnvelope(
        company="acme",
        task_id="task-1",
        step_id="implementation",
        role="engineer",
        model_profile="code-worker",
        inputs={
            "goal": "Change app.txt",
            "acceptance": "app.txt contains after",
            "_upstream": {"design": {"approved": True}},
        },
        allowed_tools=("repository.write",),
    )


def _write_state(workspace: Path, state: dict) -> None:
    state_dir = workspace / ".acme-loop"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "state.json").write_text(json.dumps(state))


def test_loop_worker_passes_with_isolated_diff_and_trusted_policy(
    tmp_path, monkeypatch
):
    source = _source_repository(tmp_path)
    captured = {}
    monkeypatch.setenv("PRODUCTION_SECRET", "must-not-leak")

    def run(config, workspace, environment, resume):
        captured.update(
            config=config,
            workspace=workspace,
            environment=environment,
            resume=resume,
        )
        (workspace / "app.txt").write_text("after\n")
        state = {
            "run_id": "run-1",
            "status": "PASSED",
            "iteration": 2,
            "reason": "verifier passed",
            "feedback": "LOOP_VERDICT: PASS",
            "history": [],
        }
        _write_state(workspace, state)
        return state

    worker = LoopWorker(
        source,
        tmp_path / "workspaces",
        policy=LoopPolicy(
            executor_provider="claude",
            verifier_provider="codex",
            max_iterations=3,
            max_minutes=10,
            step_timeout_seconds=60,
        ),
        runner=run,
    )
    result = worker.run(_envelope())

    assert result.status == "ok"
    assert result.artifact["loop"]["status"] == "PASSED"
    assert result.artifact["changed_files"] == ["app.txt"]
    assert "-before" in result.artifact["diff"]
    assert "+after" in result.artifact["diff"]
    assert (source / "app.txt").read_text() == "before\n"
    assert captured["config"]["executor"] == {"provider": "claude"}
    assert captured["config"]["verifier"]["provider"] == "codex"
    assert captured["config"]["loop"]["max_iterations"] == 3
    assert "command" not in captured["config"]["executor"]
    assert "PRODUCTION_SECRET" not in captured["environment"]
    assert captured["resume"] is False


def test_exhausted_state_is_deferred_and_reused_without_extra_attempt(tmp_path):
    source = _source_repository(tmp_path)
    calls = []

    def run(config, workspace, environment, resume):
        calls.append(resume)
        state = {
            "run_id": "run-exhausted",
            "status": "EXHAUSTED",
            "iteration": 4,
            "reason": "iteration limit reached",
            "feedback": "tests still fail",
            "history": [],
        }
        _write_state(workspace, state)
        return state

    worker = LoopWorker(source, tmp_path / "workspaces", runner=run)
    first = worker.run(_envelope())
    second = worker.run(_envelope())

    assert first.status == second.status == "deferred"
    assert second.usage["loop_run_id"] == "run-exhausted"
    assert calls == [False]


def test_repository_evidence_includes_agent_commits(tmp_path):
    source = _source_repository(tmp_path)

    def run(config, workspace, environment, resume):
        (workspace / "app.txt").write_text("committed result\n")
        _git("config", "user.email", "agent@example.invalid", cwd=workspace)
        _git("config", "user.name", "Agent", cwd=workspace)
        _git("add", "app.txt", cwd=workspace)
        _git("commit", "-q", "-m", "agent result", cwd=workspace)
        return {
            "run_id": "run-commit",
            "status": "PASSED",
            "iteration": 1,
            "reason": "verifier passed",
            "feedback": "LOOP_VERDICT: PASS",
            "history": [],
        }

    result = LoopWorker(
        source, tmp_path / "workspaces", runner=run
    ).run(_envelope())

    assert result.status == "ok"
    assert result.artifact["base_commit"] != result.artifact["head_commit"]
    assert result.artifact["changed_files"] == ["app.txt"]
    assert "+committed result" in result.artifact["diff"]


def test_stopped_state_resumes_same_workspace(tmp_path):
    source = _source_repository(tmp_path)
    calls = []

    def run(config, workspace, environment, resume):
        calls.append((workspace, resume))
        status = "STOPPED" if len(calls) == 1 else "PASSED"
        state = {
            "run_id": "run-resumable",
            "status": status,
            "iteration": len(calls),
            "reason": "interrupted" if status == "STOPPED" else "verifier passed",
            "feedback": "",
            "history": [],
        }
        _write_state(workspace, state)
        return state

    worker = LoopWorker(source, tmp_path / "workspaces", runner=run)
    assert worker.run(_envelope()).status == "deferred"
    assert worker.run(_envelope()).status == "ok"
    assert calls[0][0] == calls[1][0]
    assert calls[0][1] is False
    assert calls[1][1] is True


def test_task_input_cannot_override_commands_or_limits(tmp_path):
    source = _source_repository(tmp_path)
    seen = {}
    envelope = _envelope()
    envelope.inputs.update({
        "executor": {"command": ["sh", "-c", "dangerous"]},
        "max_iterations": 9999,
    })

    def run(config, workspace, environment, resume):
        seen.update(config)
        return {
            "run_id": "safe",
            "status": "EXHAUSTED",
            "iteration": 1,
            "reason": "iteration limit reached",
            "feedback": "",
            "history": [],
        }

    policy = LoopPolicy(max_iterations=2)
    result = LoopWorker(
        source, tmp_path / "workspaces", policy=policy, runner=run
    ).run(envelope)

    assert result.status == "deferred"
    assert seen["loop"]["max_iterations"] == 2
    assert seen["executor"] == {"provider": "codex"}


def test_policy_rejects_unsupported_provider():
    try:
        LoopPolicy(executor_provider="custom")
    except ValueError as exc:
        assert "executor_provider" in str(exc)
    else:
        raise AssertionError("unsupported provider was accepted")


def test_workspace_root_cannot_be_inside_source(tmp_path):
    source = _source_repository(tmp_path)
    try:
        LoopWorker(source, source / ".workspaces")
    except ValueError as exc:
        assert "inside source_repository" in str(exc)
    else:
        raise AssertionError("workspace inside source repository was accepted")
