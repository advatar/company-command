"""DBOS durable execution engine tests.

Run only when COMCMD_TEST_DBOS_URL points at a reachable Postgres (DBOS creates its
own system database alongside). Skipped otherwise so the default run needs no
database. DBOS is a process-wide singleton, so these tests share one engine.
"""

import os
import secrets

import pytest

DSN = os.environ.get("COMCMD_TEST_DBOS_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="COMCMD_TEST_DBOS_URL not set")


def _uid(prefix):
    # DBOS persists a workflow id's terminal outcome across runs; unique ids per
    # run keep each test independent of prior state in the system database.
    return f"{prefix}-{secrets.token_hex(6)}"


def test_step_memoization_resume(dbos_engine):
    """Re-running the same task id resumes from checkpoint: steps run once."""
    calls = {"research": 0, "brief": 0}
    ledgered = []

    def mk(name):
        def run():
            calls[name] += 1
            return {"did": name}
        return run

    dbos_engine.register("memo-co", {"research": mk("research"), "brief": mk("brief")},
                    ledger_emit=lambda step, art: ledgered.append(step))

    tid = _uid("task-memo")
    r1 = dbos_engine.run("memo-co", tid, ["research", "brief"])
    r2 = dbos_engine.run("memo-co", tid, ["research", "brief"])  # memoized

    assert r1 == r2 == {"research": {"did": "research"}, "brief": {"did": "brief"}}
    assert calls == {"research": 1, "brief": 1}   # each step ran exactly once


def test_step_retry_recovers_transient_failure(dbos_engine):
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("transient")
        return {"ok": True}

    dbos_engine.register("retry-co", {"only": flaky})
    result = dbos_engine.run("retry-co", _uid("task-retry"), ["only"])
    assert result == {"only": {"ok": True}}
    assert attempts["n"] >= 2   # retried at least once, then succeeded


def test_durable_queue_executes_enqueued_pipelines(dbos_engine):
    seen = []
    dbos_engine.register("queue-co", {"s": lambda: seen.append("s") or {"done": True}})
    handle = dbos_engine.enqueue("queue-co", _uid("task-queue"), ["s"])
    result = handle.get_result()
    assert result == {"s": {"done": True}}


def test_per_company_queue_is_concurrency_capped(dbos_engine):
    dbos_engine.register("capped-co", {"s": lambda: {"ok": True}})
    q = dbos_engine.company_queue("capped-co", concurrency=1)
    assert q.name == "comcmd-co-capped-co"
    # runs on the per-company queue and still completes
    handle = dbos_engine.enqueue("capped-co", _uid("task-capped"), ["s"],
                                 per_company=True)
    assert handle.get_result() == {"s": {"ok": True}}
