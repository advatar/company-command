import secrets
from pathlib import Path

import pytest

from comcmd.compile.compiler import compile_company
from comcmd.gateway.enrollment import CredentialStore
from comcmd.gateway.gate import Gateway
from comcmd.gateway.intents import ActionIntent
from comcmd.gateway.webauthn_verifier import WebAuthnVerifier
from comcmd.kernel.executor import Executor
from comcmd.kernel.ledger import Ledger
from comcmd.kernel.records import TaskState
from comcmd.kernel.workflow import WorkflowRunner
from comcmd.spec.loader import load_company_spec
from comcmd.workers.api import TaskEnvelope, WorkerResult
from comcmd.workers.native import NativeWorker
from tests.support.authenticator import SoftAuthenticator

EXAMPLE = Path(__file__).resolve().parents[1] / "companies" / "example-studio"
RP_ID = "comcmd.local"
ORIGIN = "https://comcmd.local"


def _enroll(store, principal, user_verified=True):
    dev = SoftAuthenticator(RP_ID, ORIGIN, user_verified=user_verified)
    challenge = secrets.token_bytes(32)
    store.enroll_registration(principal, credential=dev.register(challenge),
                              expected_challenge=challenge, rp_id=RP_ID, origin=ORIGIN)
    return dev


def _assert_for(dev, gateway, digest):
    challenge = gateway.challenge_for(digest)
    assert challenge is not None
    return dev.authenticate(challenge)


def _skills():
    def s(name):
        return lambda env: WorkerResult(status="ok", artifact={"did": name})
    return {"research": s("research"), "brief": s("brief")}


def _harness():
    spec = load_company_spec(EXAMPLE)
    rev = compile_company(spec).raise_if_failed()
    ledger = Ledger(":memory:")
    creds = CredentialStore()
    verifier = WebAuthnVerifier(creds, rp_id=RP_ID, origin=ORIGIN)
    gateway = Gateway(ledger, {a.id: a for a in spec.actions}, verifier=verifier)
    published = []
    executor = Executor(ledger, {"publishing.publish": lambda i: published.append(i.action_digest) or {"ok": True}})
    runner = WorkflowRunner(rev, ledger, NativeWorker(skills=_skills()), gateway, executor)
    return runner, gateway, creds, ledger, rev, published


def test_full_approval_ceremony_publishes_through_gateway():
    runner, gateway, creds, ledger, rev, published = _harness()
    board = _enroll(creds, "human:board")

    handle = runner.start("validate-product")
    assert handle.state == TaskState.WAITING_FOR_HUMAN
    digest = handle.waiting_on["intent_digest"]

    assertion = _assert_for(board, gateway, digest)
    done = runner.approve_step(handle.task_id, "validate-product", "approve", assertion)

    assert done.state == TaskState.SUCCEEDED
    assert len(published) == 1                 # effect happened exactly once
    assert ledger.verify_chain(rev.company_name)


def test_approval_denied_for_unenrolled_approver_keeps_task_parked():
    runner, gateway, creds, ledger, rev, published = _harness()
    _enroll(creds, "human:board")
    stranger = SoftAuthenticator(RP_ID, ORIGIN)  # not enrolled

    handle = runner.start("validate-product")
    digest = handle.waiting_on["intent_digest"]
    assertion = _assert_for(stranger, gateway, digest)
    still = runner.approve_step(handle.task_id, "validate-product", "approve", assertion)

    assert still.state == TaskState.WAITING_FOR_HUMAN
    assert published == []                     # no effect without valid approval


def test_no_worker_effect_without_gateway():
    # The publish tool is never invoked by the worker; the only path to it is the
    # executor, which requires a gateway-minted capability. Before approval, the
    # published sink is empty even though research+brief ran.
    runner, gateway, creds, ledger, rev, published = _harness()
    _enroll(creds, "human:board")
    handle = runner.start("validate-product")
    assert handle.state == TaskState.WAITING_FOR_HUMAN
    assert published == []
