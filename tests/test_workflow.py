from pathlib import Path

import pytest

from acme.compile.compiler import compile_company
from acme.gateway.gate import Gateway
from acme.kernel.ledger import Ledger
from acme.kernel.records import TaskState
from acme.kernel.workflow import WorkflowRunner, WorkflowError
from acme.spec.loader import load_company_spec
from acme.workers.api import TaskEnvelope, WorkerResult
from acme.workers.native import NativeWorker

EXAMPLE = Path(__file__).resolve().parents[1] / "companies" / "example-studio"


def _revision():
    spec = load_company_spec(EXAMPLE)
    r = compile_company(spec)
    assert r.ok, r.errors
    return spec, r.revision


def _runner(effects, crash_on=None):
    """A runner whose 'research'/'brief' skills record a side effect.

    If crash_on names a step, that step raises on its FIRST execution to
    simulate a process crash, then succeeds on retry.
    """
    spec, rev = _revision()
    ledger = Ledger(":memory:")
    gateway = Gateway(ledger, {a.id: a for a in spec.actions})

    state = {"crashed": False}

    def make_skill(name):
        def skill(env: TaskEnvelope) -> WorkerResult:
            if crash_on == name and not state["crashed"]:
                state["crashed"] = True
                raise RuntimeError(f"simulated crash during {name}")
            effects.append(name)
            return WorkerResult(status="ok", artifact={"did": name})
        return skill

    worker = NativeWorker(skills={"research": make_skill("research"),
                                  "brief": make_skill("brief")})
    return WorkflowRunner(rev, ledger, worker, gateway), ledger, rev


def test_runs_to_human_gate_and_parks():
    effects = []
    runner, ledger, rev = _runner(effects)
    handle = runner.start("validate-product")
    assert handle.state == TaskState.WAITING_FOR_HUMAN
    assert effects == ["research", "brief"]
    assert handle.waiting_on["policy"] == "publish-external-copy"
    assert ledger.verify_chain(rev.company_name)


def test_crash_then_resume_does_not_duplicate_effects():
    effects = []
    runner, ledger, rev = _runner(effects, crash_on="brief")

    # First attempt crashes during 'brief' (after 'research' already committed).
    # A hard crash propagates raw: the process dies mid-step, so no
    # step_succeeded event is written for 'brief'.
    with pytest.raises(RuntimeError):
        runner.start("validate-product")
    assert effects == ["research"]

    # Resume: 'research' must NOT re-run; 'brief' completes; task parks at gate.
    task_id = _only_task_id(ledger, rev.company_name)
    handle = runner.resume(task_id, "validate-product")
    assert handle.state == TaskState.WAITING_FOR_HUMAN
    # research recorded exactly once across crash + resume
    assert effects == ["research", "brief"]
    assert ledger.verify_chain(rev.company_name)


def test_resume_is_idempotent_when_already_complete():
    effects = []
    runner, ledger, rev = _runner(effects)
    handle = runner.start("validate-product")
    task_id = _only_task_id(ledger, rev.company_name)
    # Resuming a parked task re-drives but re-runs nothing already done.
    again = runner.resume(task_id, "validate-product")
    assert again.state == TaskState.WAITING_FOR_HUMAN
    assert effects == ["research", "brief"]  # no duplication


def _only_task_id(ledger, company):
    ids = {se.event.task_id for se in ledger.read(company) if se.event.task_id}
    assert len(ids) == 1, ids
    return next(iter(ids))
