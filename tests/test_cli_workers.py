from comcmd.workers.api import TaskEnvelope
from comcmd.workers.cli_agents import CodexWorker, OpenHandsWorker, _extract_json


def _env():
    return TaskEnvelope(company="c1", task_id="t1", step_id="design", role="game-director",
                        model_profile=None,
                        inputs={"_upstream": {"market": {"family": "puzzle_box"}}},
                        allowed_tools=("design.spec",))


def test_prompt_includes_role_step_and_upstream():
    w = CodexWorker(available=True, runner=lambda argv, prompt: "{}")
    p = w.build_prompt(_env())
    assert "game-director" in p and "design" in p and "puzzle_box" in p
    assert "design.spec" in p


def test_parses_json_artifact_from_stdout():
    def fake(argv, prompt):
        assert argv[:2] == ["codex", "exec"]
        return 'thinking...\n{"levels": 24, "title": "puzzle_box-mvp"}\ndone'
    w = CodexWorker(available=True, runner=fake)
    r = w.run(_env())
    assert r.status == "ok" and r.artifact["levels"] == 24


def test_non_json_output_becomes_text_artifact():
    w = CodexWorker(available=True, runner=lambda argv, prompt: "just prose, no json")
    r = w.run(_env())
    assert r.status == "ok" and r.artifact["text"] == "just prose, no json"


def test_unavailable_binary_defers_safely():
    w = OpenHandsWorker(available=False)
    r = w.run(_env())
    assert r.status == "deferred" and r.artifact is None


def test_runner_error_fails_closed():
    def boom(argv, prompt):
        raise RuntimeError("exit 1")
    w = CodexWorker(available=True, runner=boom)
    r = w.run(_env())
    assert r.status == "error" and r.artifact is None


def test_extract_json_picks_last_object():
    assert _extract_json('a {"x":1} b {"y":2} c') == {"y": 2}
    assert _extract_json("no json here") is None
