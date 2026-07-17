"""AutoSteam CompanyPack: proves the framework is generic.

A second company, unrelated to example-studio, runs end-to-end on the same
kernel/gateway/executor purely from `companies/auto-steam/` (declared manifest +
deterministic domain skills). Nothing about the studio lives in comcmd/*.
"""

import secrets
from pathlib import Path

from comcmd.gateway.enrollment import CredentialStore
from comcmd.gateway.webauthn_verifier import WebAuthnVerifier
from comcmd.kernel.records import TaskState
from comcmd.pack import build_runner, load_pack
from tests.support.authenticator import SoftAuthenticator

PACK_DIR = Path(__file__).resolve().parents[1] / "companies" / "auto-steam"
RP_ID = "comcmd.local"
ORIGIN = "https://comcmd.local"


def _enroll(store, principal):
    dev = SoftAuthenticator(RP_ID, ORIGIN)
    ch = secrets.token_bytes(32)
    store.enroll_registration(principal, credential=dev.register(ch),
                              expected_challenge=ch, rp_id=RP_ID, origin=ORIGIN)
    return dev


def test_autosteam_compiles_and_is_distinct_from_example():
    pack = load_pack(PACK_DIR)
    from comcmd.compile.compiler import compile_company
    rev = compile_company(pack.spec).raise_if_failed()
    assert rev.company_name == "auto-steam"
    # a genuinely different roster/workflow than example-studio
    role_ids = {r["id"] for r in rev.compiled["roles"]}
    assert role_ids == {"market-analyst", "game-director", "qa-engineer",
                        "compliance-officer"}


def test_autosteam_runs_to_gate_with_real_domain_artifacts():
    pack = load_pack(PACK_DIR)
    ctx = build_runner(pack)
    handle = ctx.runner.start("ship-title")

    assert handle.state == TaskState.WAITING_FOR_HUMAN
    # deterministic domain outputs flowed through the pipeline
    assert handle.artifacts["market"]["greenlit"] is True
    assert handle.artifacts["design"]["family"] == "puzzle_box"
    assert handle.artifacts["qa"]["passed"] is True
    assert handle.artifacts["compliance"]["human_approval_required"] is True
    assert handle.waiting_on["policy"] == "publish-to-steam"


def test_autosteam_release_publishes_once_after_passkey_approval():
    pack = load_pack(PACK_DIR)
    creds = CredentialStore()
    lead = _enroll(creds, "human:studio-lead")
    verifier = WebAuthnVerifier(creds, rp_id=RP_ID, origin=ORIGIN)
    ctx = build_runner(pack, verifier=verifier)

    handle = ctx.runner.start("ship-title")
    digest = handle.waiting_on["intent_digest"]
    assertion = lead.authenticate(ctx.gateway.challenge_for(digest))

    done = ctx.runner.approve_step(handle.task_id, "ship-title", "release", assertion)
    assert done.state == TaskState.SUCCEEDED
    assert ctx.ledger.verify_chain(ctx.revision.company_name)

    # the steam.publish effect happened exactly once, only via the gateway
    from comcmd.kernel.records import EventType
    executed = [e.event for e in ctx.ledger.read(ctx.revision.company_name)
                if e.event.type == EventType.execution_receipt
                and e.event.payload.get("executed") is True]
    assert len(executed) == 1
