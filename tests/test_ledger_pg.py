"""Conformance tests for the Postgres durable ledger.

Runs only when COMCMD_TEST_DATABASE_URL points at a reachable Postgres; otherwise
skipped, so the default test run needs no database. Each test uses a unique
company id, so the shared table stays isolated without truncation.
"""

import os
import secrets

import pytest

from comcmd.kernel.records import Event, EventType, TaskState

DSN = os.environ.get("COMCMD_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="COMCMD_TEST_DATABASE_URL not set")


@pytest.fixture
def pg():
    from comcmd.kernel.ledger_pg import PostgresLedger
    led = PostgresLedger(DSN)
    yield led
    led.close()


def _co():
    return "co-" + secrets.token_hex(8)


def _ev(company, i):
    return Event(type=EventType.step_succeeded, company=company, task_id="t1",
                 payload={"step": f"s{i}"})


def test_append_verify_and_order(pg):
    co = _co()
    for i in range(5):
        pg.append(_ev(co, i))
    assert pg.verify_chain(co) is True
    assert [se.event.payload["step"] for se in pg.read(co)] == [f"s{i}" for i in range(5)]


def test_chain_links_prev_seal(pg):
    co = _co()
    a = pg.append(_ev(co, 0))
    b = pg.append(_ev(co, 1))
    assert b.prev_seal == a.seal
    assert a.prev_seal.endswith("0" * 64)


def test_tamper_detected(pg):
    import psycopg

    co = _co()
    for i in range(3):
        pg.append(_ev(co, i))
    assert pg.verify_chain(co) is True
    with psycopg.connect(DSN) as c:
        c.execute(
            "UPDATE comcmd_events SET body=%s WHERE company=%s AND task_id='t1' "
            "AND body LIKE %s",
            ('{"type":"step_succeeded","company":"%s","task_id":"t1",'
             '"payload":{"step":"TAMPERED"}}' % co, co, '%"s1"%'))
        c.commit()
    assert pg.verify_chain(co) is False


def test_crash_resume_over_postgres(pg):
    """The Phase 0 exit gate, but with the durable Postgres ledger underneath."""
    from pathlib import Path

    from comcmd.compile.compiler import compile_company
    from comcmd.gateway.gate import Gateway
    from comcmd.kernel.workflow import WorkflowRunner
    from comcmd.spec.loader import load_company_spec
    from comcmd.workers.api import TaskEnvelope, WorkerResult
    from comcmd.workers.native import NativeWorker

    example = Path(__file__).resolve().parents[1] / "companies" / "example-studio"
    spec = load_company_spec(example)
    spec.metadata.name = _co()  # unique company so the shared table is isolated
    rev = compile_company(spec).raise_if_failed()

    effects = []
    crashed = {"v": False}

    def skill(name):
        def run(env: TaskEnvelope) -> WorkerResult:
            if name == "brief" and not crashed["v"]:
                crashed["v"] = True
                raise RuntimeError("simulated crash")
            effects.append(name)
            return WorkerResult(status="ok", artifact={"did": name})
        return run

    gw = Gateway(pg, {a.id: a for a in spec.actions})
    runner = WorkflowRunner(rev, pg, NativeWorker(skills={"research": skill("research"),
                                                          "brief": skill("brief")}), gw)

    with pytest.raises(RuntimeError):
        runner.start("validate-product")
    assert effects == ["research"]

    task_ids = {se.event.task_id for se in pg.read(rev.company_name) if se.event.task_id}
    handle = runner.resume(next(iter(task_ids)), "validate-product")
    assert handle.state == TaskState.WAITING_FOR_HUMAN
    assert effects == ["research", "brief"]  # research not duplicated
    assert pg.verify_chain(rev.company_name)
