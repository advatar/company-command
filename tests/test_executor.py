from comcmd.gateway.gate import Capability
from comcmd.gateway.intents import ActionIntent
from comcmd.kernel.executor import Executor
from comcmd.kernel.ledger import Ledger


def _intent(**kw):
    base = dict(company="c1", task_id="t1", step_id="s1", requested_by="w",
                action_id="publish", tool="publishing.publish")
    base.update(kw)
    return ActionIntent(**base)


def _cap(intent, tool=None):
    return Capability(capability_id="cap_x", intent_digest=intent.action_digest,
                      tool=tool or intent.tool, scope={}, ttl="10m")


def test_executes_once_and_dedupes_on_replay():
    sink = []
    led = Ledger(":memory:")
    ex = Executor(led, {"publishing.publish": lambda i: sink.append(i.action_digest) or {"ok": True}})
    intent = _intent()
    cap = _cap(intent)

    first = ex.execute(cap, intent)
    assert first.executed and not first.duplicate
    # Replay after a "crash" between authorize and execute: no second effect.
    second = ex.execute(cap, intent)
    assert second.duplicate and not second.executed
    assert sink == [intent.action_digest]  # ran exactly once


def test_capability_digest_mismatch_refused():
    led = Ledger(":memory:")
    ex = Executor(led, {"publishing.publish": lambda i: {}})
    intent = _intent()
    wrong = Capability(capability_id="cap_y", intent_digest="sha256:deadbeef",
                       tool="publishing.publish", scope={}, ttl="10m")
    out = ex.execute(wrong, intent)
    assert not out.executed and out.receipt.decision == "refused"


def test_tool_mismatch_refused():
    led = Ledger(":memory:")
    ex = Executor(led, {"publishing.publish": lambda i: {}})
    intent = _intent()
    out = ex.execute(_cap(intent, tool="finance.pay"), intent)
    assert not out.executed and out.receipt.decision == "refused"


def test_no_handler_refused():
    led = Ledger(":memory:")
    ex = Executor(led, {})  # nothing registered
    intent = _intent()
    out = ex.execute(_cap(intent), intent)
    assert not out.executed and "no handler" in out.receipt.reason
