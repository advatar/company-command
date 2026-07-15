from acme.gateway.gate import Gateway
from acme.gateway.intents import ActionIntent
from acme.kernel.ledger import Ledger
from acme.spec.models import Action, Approval, Risk
from acme.telemetry import InMemoryTelemetry, NullTelemetry, _scrub


def _intent(action_id, tool, **kw):
    return ActionIntent(company="c1", task_id="t1", step_id="s1",
                        requested_by="agent:w", action_id=action_id, tool=tool, **kw)


def _actions():
    return {
        "read": Action(id="read", tool="r", risk=Risk.observe),
        "publish": Action(id="publish", tool="p", risk=Risk.external_reversible,
                          idempotency="k",
                          approval=Approval(require="passkey", roles=["human:board"])),
    }


def test_gateway_emits_decision_telemetry_without_secrets():
    tel = InMemoryTelemetry()
    gw = Gateway(Ledger(":memory:"), _actions(), telemetry=tel)
    gw.decide(_intent("read", "r"))                     # auto
    gw.decide(_intent("publish", "p"))                  # require_approval

    decisions = tel.events_named("gate.decision")
    assert {d["decision"] for d in decisions} >= {"authorized", "require_approval"}
    for d in decisions:
        # only identifiers — no challenge/assertion/capability material
        assert set(d) <= {"company", "decision", "tier", "action", "digest"}


def test_scrub_drops_forbidden_keys():
    cleaned = _scrub({"action": "x", "challenge": b"secret", "token": "abc",
                      "tier": "A2"})
    assert cleaned == {"action": "x", "tier": "A2"}


def test_null_telemetry_is_noop():
    t = NullTelemetry()
    t.event("x", a=1)
    with t.span("s"):
        pass
