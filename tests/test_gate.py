import pytest

from acme.gateway.gate import Gateway
from acme.gateway.intents import ActionIntent
from acme.gateway.policy import Bounds, Tier
from acme.gateway.verifier import AlwaysApproveVerifier, DenyByDefaultVerifier
from acme.kernel.ledger import Ledger
from acme.spec.models import Action, Approval, Risk


def _actions():
    return {
        "read-x": Action(id="read-x", tool="research.search", risk=Risk.observe),
        "draft-x": Action(id="draft-x", tool="artifacts.write",
                          risk=Risk.bounded_internal,
                          approval=Approval(require="passkey", roles=["human:board"])),
        "publish": Action(id="publish", tool="publishing.publish",
                          risk=Risk.external_reversible,
                          idempotency="dedupe_by_content_hash",
                          approval=Approval(require="passkey", roles=["human:board"])),
        "pay": Action(id="pay", tool="finance.pay", risk=Risk.consequential,
                      idempotency="k",
                      approval=Approval(require="hardware_passkey", quorum=2,
                                        roles=["human:board", "human:finance"])),
        "forbidden": Action(id="forbidden", tool="finance.pay", risk=Risk.prohibited),
    }


def _intent(action_id, tool, **kw):
    return ActionIntent(company="c1", task_id="t1", step_id="s1",
                        requested_by="agent:worker", action_id=action_id,
                        tool=tool, **kw)


def _gw(verifier=None, bounds=None):
    return Gateway(Ledger(":memory:"), _actions(), verifier=verifier, bounds=bounds)


def test_a0_auto_authorizes():
    out = _gw().decide(_intent("read-x", "research.search"))
    assert out.decision == "auto" and out.tier == Tier.A0
    assert out.capability is not None


def test_a2_requires_approval_and_deny_by_default():
    out = _gw().decide(_intent("publish", "publishing.publish"))
    assert out.decision == "require_approval" and out.tier == Tier.A2
    assert out.capability is None
    # A bogus assertion against the deny-by-default verifier does not authorize;
    # the approval stays open (a legitimate approver may still act).
    out2 = _gw().decide(_intent("publish", "publishing.publish"), assertion={"x": 1})
    assert out2.decision == "require_approval"
    assert out2.capability is None


def test_a2_authorized_with_eligible_approver():
    out = _gw(verifier=AlwaysApproveVerifier()).decide(
        _intent("publish", "publishing.publish"),
        assertion={"principal": "human:board"})
    assert out.decision == "authorized"
    assert out.capability is not None
    assert out.capability.single_use is True


def test_a2_ineligible_approver_not_authorized():
    out = _gw(verifier=AlwaysApproveVerifier()).decide(
        _intent("publish", "publishing.publish"),
        assertion={"principal": "human:intruder"})
    assert out.decision == "require_approval"  # not authorized


def test_a3_requires_two_distinct_approvers():
    gw = _gw(verifier=AlwaysApproveVerifier())
    intent = _intent("pay", "finance.pay", amount=100.0)
    # open the approval
    assert gw.decide(intent).decision == "require_approval"
    # first approver: still short of quorum
    o1 = gw.submit_approval(intent, {"principal": "human:board"})
    assert o1.decision == "require_approval"
    # same approver again: does not count twice
    o1b = gw.submit_approval(intent, {"principal": "human:board"})
    assert o1b.decision == "require_approval"
    # second distinct approver: quorum met -> authorized
    o2 = gw.submit_approval(intent, {"principal": "human:finance"})
    assert o2.tier == Tier.A3 and o2.decision == "authorized"
    assert o2.capability is not None


def test_a3_single_approver_denied():
    acts = _actions()
    acts["pay"] = Action(id="pay", tool="finance.pay", risk=Risk.consequential,
                         idempotency="k",
                         approval=Approval(require="hardware_passkey", quorum=1,
                                           roles=["human:board"]))
    gw = Gateway(Ledger(":memory:"), acts, verifier=AlwaysApproveVerifier())
    out = gw.decide(_intent("pay", "finance.pay"), assertion={"sig": "ok"})
    assert out.decision == "deny"
    assert "dual control" in out.reason


def test_a4_prohibited_denied():
    out = _gw().decide(_intent("forbidden", "finance.pay"))
    assert out.decision == "deny" and out.tier == Tier.A4


def test_unknown_action_denied():
    out = _gw().decide(_intent("ghost", "whatever"))
    assert out.decision == "deny"


def test_tool_mismatch_denied():
    out = _gw().decide(_intent("publish", "finance.pay"))
    assert out.decision == "deny"


def test_bounded_auto_escalates_when_over_amount():
    gw = _gw(bounds={"draft-x": Bounds(max_amount=10.0)})
    # within bound -> auto
    assert gw.decide(_intent("draft-x", "artifacts.write", amount=5.0)).decision == "auto"
    # over bound -> escalates to A2 approval
    out = gw.decide(_intent("draft-x", "artifacts.write", amount=50.0))
    assert out.decision == "require_approval" and out.tier == Tier.A2
