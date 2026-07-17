"""Cross-process approval via Postgres-backed credential + approval stores.

Two independent Gateway instances (standing in for two processes/nodes) share
the durable stores: instance A opens the approval, instance B completes it with
a WebAuthn assertion. Gated on COMCMD_TEST_DATABASE_URL.
"""

import os
import secrets

import pytest

from comcmd.kernel.ledger import Ledger
from comcmd.spec.models import Action, Approval, Risk

DSN = os.environ.get("COMCMD_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="COMCMD_TEST_DATABASE_URL not set")

RP_ID = "comcmd.local"
ORIGIN = "https://comcmd.local"


@pytest.fixture
def stores():
    from comcmd.gateway.stores_pg import PgApprovalStore, PgCredentialStore
    suffix = secrets.token_hex(4)
    creds = PgCredentialStore(DSN, table=f"comcmd_credentials_{suffix}")
    appr_a = PgApprovalStore(DSN, table=f"comcmd_approvals_{suffix}")
    appr_b = PgApprovalStore(DSN, table=f"comcmd_approvals_{suffix}")
    yield creds, appr_a, appr_b
    creds.close(); appr_a.close(); appr_b.close()


def _action():
    return {"publish": Action(id="publish", tool="pub", risk=Risk.external_reversible,
                              idempotency="k",
                              approval=Approval(require="passkey",
                                                roles=["human:board"]))}


def test_credential_persists_and_verifies(stores):
    from comcmd.gateway.webauthn_verifier import WebAuthnVerifier
    from tests.support.authenticator import SoftAuthenticator
    creds, _, _ = stores
    dev = SoftAuthenticator(RP_ID, ORIGIN)
    ch = secrets.token_bytes(32)
    creds.enroll_registration("human:board", credential=dev.register(ch),
                              expected_challenge=ch, rp_id=RP_ID, origin=ORIGIN)
    # a fresh verifier reading the same store verifies an assertion
    v = WebAuthnVerifier(creds, rp_id=RP_ID, origin=ORIGIN)
    challenge = secrets.token_bytes(32)
    d = v.verify(approval_request={"_challenge": challenge},
                 assertion=dev.authenticate(challenge))
    assert d.approved and d.principal == "human:board"


def test_approval_opened_on_A_completed_on_B(stores):
    from comcmd.gateway.gate import Gateway
    from comcmd.gateway.intents import ActionIntent
    from comcmd.gateway.webauthn_verifier import WebAuthnVerifier
    from tests.support.authenticator import SoftAuthenticator

    creds, appr_a, appr_b = stores
    dev = SoftAuthenticator(RP_ID, ORIGIN)
    ch = secrets.token_bytes(32)
    creds.enroll_registration("human:board", credential=dev.register(ch),
                              expected_challenge=ch, rp_id=RP_ID, origin=ORIGIN)

    verifier = WebAuthnVerifier(creds, rp_id=RP_ID, origin=ORIGIN)
    intent = ActionIntent(company="c1", task_id="t1", step_id="s1",
                          requested_by="agent:w", action_id="publish", tool="pub")

    # instance A opens the approval (durable)
    gw_a = Gateway(Ledger(":memory:"), _action(), approval_store=appr_a)
    out_a = gw_a.decide(intent)
    assert out_a.decision == "require_approval"

    # instance B (separate process) reads the challenge and completes it
    gw_b = Gateway(Ledger(":memory:"), _action(), verifier=verifier,
                   approval_store=appr_b)
    challenge = gw_b.challenge_for(intent.action_digest)
    assert challenge is not None
    out_b = gw_b.submit_approval(intent, dev.authenticate(challenge))
    assert out_b.decision == "authorized"
    assert out_b.capability is not None
