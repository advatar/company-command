import copy
from pathlib import Path

import pytest

from comcmd.compile.compiler import compile_company
from comcmd.spec.loader import load_company_spec
from comcmd.spec.models import CompanySpec

EXAMPLE = Path(__file__).resolve().parents[1] / "companies" / "example-studio"


def _spec_dict():
    return load_company_spec(EXAMPLE).to_canonical_dict()


def _compile(d):
    return compile_company(CompanySpec.model_validate(d))


def test_example_compiles_and_is_content_addressed():
    spec = load_company_spec(EXAMPLE)
    r1 = compile_company(spec)
    r2 = compile_company(spec)
    assert r1.ok, r1.errors
    assert r1.revision.revision_id == r2.revision.revision_id
    assert r1.revision.revision_id.startswith("rev_")


def test_unknown_tool_rejected():
    d = _spec_dict()
    d["roles"][0]["tools"]["allow"].append("does.not.exist")
    r = _compile(d)
    assert not r.ok
    assert any(e.code == "E-REF-TOOL" for e in r.errors)


def test_unknown_runas_role_rejected():
    d = _spec_dict()
    d["workflows"][0]["steps"][0]["runAs"] = "ghost"
    r = _compile(d)
    assert not r.ok
    assert any(e.code == "E-REF-ROLE" for e in r.errors)


def test_side_effecting_action_without_idempotency_rejected():
    d = _spec_dict()
    for a in d["actions"]:
        if a["id"] == "publish-external-copy":
            a.pop("idempotency", None)
    r = _compile(d)
    assert not r.ok
    assert any(e.code == "E-IDEMPOTENCY" for e in r.errors)


def test_high_risk_action_without_approver_rejected():
    d = _spec_dict()
    for a in d["actions"]:
        if a["id"] == "publish-external-copy":
            a.pop("approval", None)
    r = _compile(d)
    assert not r.ok
    assert any(e.code == "E-APPROVER" for e in r.errors)


def test_consequential_action_needs_hardware_key():
    d = _spec_dict()
    for a in d["actions"]:
        if a["id"] == "spend-money":
            a["approval"]["require"] = "passkey"  # too weak for A3
    r = _compile(d)
    assert not r.ok
    assert any(e.code == "E-CAP-DEFAULTALLOW" for e in r.errors)


def test_humangate_unknown_policy_rejected():
    d = _spec_dict()
    for s in d["workflows"][0]["steps"]:
        if s.get("type") == "humanGate":
            s["policy"] = "no-such-action"
    r = _compile(d)
    assert not r.ok
    assert any(e.code == "E-REF-WORKFLOW" for e in r.errors)


def test_unbounded_cycle_rejected():
    d = _spec_dict()
    steps = d["workflows"][0]["steps"]
    # make research depend on brief -> research<->brief cycle, no loopBound
    for s in steps:
        if s["id"] == "research":
            s["needs"] = ["brief"]
    r = _compile(d)
    assert not r.ok
    assert any(e.code == "E-CYCLE-UNBOUNDED" for e in r.errors)


def test_bad_apiversion_rejected():
    d = _spec_dict()
    d["apiVersion"] = "comcmd.dev/v0"
    r = _compile(d)
    assert not r.ok
    assert any(e.code == "E-VERSION" for e in r.errors)


def test_reserved_engine_namespace_cannot_be_invented():
    d = _spec_dict()
    d["tools"].append("comcmd.self")
    d["actions"].append({"id": "comcmd.something", "tool": "comcmd.self",
                         "risk": "observe"})
    r = _compile(d)
    assert not r.ok
    assert any(e.code == "E-META-LOCKED" for e in r.errors)


def test_locked_meta_action_cannot_be_weakened():
    d = _spec_dict()
    d["tools"].append("comcmd.audit")
    # audit.disable is locked at 'prohibited'; declaring it reversible weakens it
    d["actions"].append({"id": "comcmd.audit.disable", "tool": "comcmd.audit",
                         "risk": "external_reversible",
                         "idempotency": "x",
                         "approval": {"require": "passkey", "roles": ["human:board"]}})
    r = _compile(d)
    assert not r.ok
    assert any(e.code == "E-TIER-LOWERED" for e in r.errors)


def test_locked_meta_action_at_locked_tier_ok():
    d = _spec_dict()
    d["tools"].append("comcmd.audit")
    d["actions"].append({"id": "comcmd.audit.disable", "tool": "comcmd.audit",
                         "risk": "prohibited"})
    r = _compile(d)
    assert r.ok, r.errors


def test_functional_domain_annotation_accepted():
    d = _spec_dict()
    for a in d["actions"]:
        if a["id"] == "spend-money":
            a["domain"] = "money"
    r = _compile(d)
    assert r.ok, r.errors


def test_unsafe_company_name_rejected():
    d = _spec_dict()
    d["metadata"]["name"] = "Robert'); DROP TABLE events;--"
    r = _compile(d)
    assert not r.ok
    assert any(e.code == "E-SLUG" for e in r.errors)


def test_trailing_newline_company_name_rejected():
    # `$` would let this pass; the \Z anchor must reject it.
    d = _spec_dict()
    d["metadata"]["name"] = "valid-co\n"
    r = _compile(d)
    assert not r.ok
    assert any(e.code == "E-SLUG" for e in r.errors)


def test_fanout_over_cap_rejected():
    d = _spec_dict()
    d["workflows"].append({
        "id": "wf-dos", "steps": [
            {"id": "f", "type": "fanout", "runAs": "researcher",
             "fanout": 9999, "aggregate": "majority"}]})
    r = _compile(d)
    assert not r.ok
    assert any(e.code == "E-FANOUT" for e in r.errors)
