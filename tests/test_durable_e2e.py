"""Unified durable execution: a CompanyPack runs the SAME governed flow on
Postgres + DBOS (durable-memoized work steps, durable event log, gateway
approval, idempotent executor). Gated on ACME_TEST_DBOS_URL.
"""

import os
import secrets
from pathlib import Path

import pytest

DSN = os.environ.get("ACME_TEST_DBOS_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="ACME_TEST_DBOS_URL not set")

PACK_DIR = Path(__file__).resolve().parents[1] / "companies" / "auto-steam"
RP_ID = "acme.local"
ORIGIN = "https://acme.local"


def test_autosteam_runs_durably_and_publishes_once(dbos_engine):
    from acme.gateway.enrollment import CredentialStore
    from acme.gateway.webauthn_verifier import WebAuthnVerifier
    from acme.kernel.records import EventType, TaskState
    from acme.pack import build_runner, load_pack
    from tests.support.authenticator import SoftAuthenticator

    pack = load_pack(PACK_DIR)
    # unique company so the shared Postgres ledger/DBOS namespace is isolated
    pack.spec.metadata.name = "auto-steam-" + secrets.token_hex(4)

    creds = CredentialStore()
    dev = SoftAuthenticator(RP_ID, ORIGIN)
    ch = secrets.token_bytes(32)
    creds.enroll_registration("human:studio-lead", credential=dev.register(ch),
                              expected_challenge=ch, rp_id=RP_ID, origin=ORIGIN)
    verifier = WebAuthnVerifier(creds, rp_id=RP_ID, origin=ORIGIN)

    ctx = build_runner(pack, ledger_url=DSN, verifier=verifier, durable_engine=dbos_engine)

    handle = ctx.runner.start("ship-title")
    assert handle.state == TaskState.WAITING_FOR_HUMAN
    assert handle.artifacts["market"]["greenlit"] is True  # durable step ran
    assert handle.artifacts["compliance"]["human_approval_required"] is True

    digest = handle.waiting_on["intent_digest"]
    assertion = dev.authenticate(ctx.gateway.challenge_for(digest))
    done = ctx.runner.approve_step(handle.task_id, "ship-title", "release", assertion)

    assert done.state == TaskState.SUCCEEDED
    assert ctx.ledger.verify_chain(ctx.revision.company_name)
    executed = [e for e in ctx.ledger.read(ctx.revision.company_name)
                if e.event.type == EventType.execution_receipt
                and e.event.payload.get("executed") is True]
    assert len(executed) == 1


def test_durable_work_step_is_memoized(dbos_engine):
    """Re-invoking the same (task, step) returns the memoized result, not a re-run."""
    calls = {"n": 0}

    def thunk():
        calls["n"] += 1
        return {"status": "ok", "artifact": {"v": 42}}

    tid = "memo-step-" + secrets.token_hex(4)
    r1 = dbos_engine.run_step(tid, "s", thunk)
    r2 = dbos_engine.run_step(tid, "s", thunk)
    assert r1 == r2 == {"status": "ok", "artifact": {"v": 42}}
    assert calls["n"] == 1  # ran once, memoized on the second call
