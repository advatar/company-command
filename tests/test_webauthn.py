import secrets

import pytest

from acme.gateway.enrollment import CredentialStore
from acme.gateway.webauthn_verifier import WebAuthnVerifier
from tests.support.authenticator import SoftAuthenticator

RP_ID = "acme.local"
ORIGIN = "https://acme.local"


def _enroll(store, principal, *, user_verified=True):
    dev = SoftAuthenticator(RP_ID, ORIGIN, user_verified=user_verified)
    challenge = secrets.token_bytes(32)
    reg = dev.register(challenge)
    store.enroll_registration(principal, credential=reg, expected_challenge=challenge,
                              rp_id=RP_ID, origin=ORIGIN)
    return dev


def _verifier(store):
    return WebAuthnVerifier(store, rp_id=RP_ID, origin=ORIGIN)


def test_valid_assertion_verifies_and_returns_principal():
    store = CredentialStore()
    dev = _enroll(store, "human:board")
    challenge = secrets.token_bytes(32)
    assertion = dev.authenticate(challenge)
    d = _verifier(store).verify(approval_request={"_challenge": challenge},
                                assertion=assertion)
    assert d.approved and d.principal == "human:board"


def test_wrong_challenge_rejected():
    store = CredentialStore()
    dev = _enroll(store, "human:board")
    assertion = dev.authenticate(secrets.token_bytes(32))  # signs challenge A
    d = _verifier(store).verify(
        approval_request={"_challenge": secrets.token_bytes(32)},  # expects B
        assertion=assertion)
    assert not d.approved


def test_unknown_credential_rejected():
    store = CredentialStore()
    _enroll(store, "human:board")
    stranger = SoftAuthenticator(RP_ID, ORIGIN)  # never enrolled
    challenge = secrets.token_bytes(32)
    d = _verifier(store).verify(approval_request={"_challenge": challenge},
                                assertion=stranger.authenticate(challenge))
    assert not d.approved and "not enrolled" in d.reason


def test_user_verification_required():
    store = CredentialStore()
    dev = _enroll(store, "human:board", user_verified=False)  # UP but not UV
    challenge = secrets.token_bytes(32)
    d = _verifier(store).verify(approval_request={"_challenge": challenge},
                                assertion=dev.authenticate(challenge))
    assert not d.approved


def test_wrong_origin_rejected():
    store = CredentialStore()
    dev = _enroll(store, "human:board")
    v = WebAuthnVerifier(store, rp_id=RP_ID, origin="https://evil.example")
    challenge = secrets.token_bytes(32)
    d = v.verify(approval_request={"_challenge": challenge},
                 assertion=dev.authenticate(challenge))
    assert not d.approved


def test_missing_bound_challenge_denies():
    store = CredentialStore()
    dev = _enroll(store, "human:board")
    d = _verifier(store).verify(approval_request={},
                                assertion=dev.authenticate(secrets.token_bytes(32)))
    assert not d.approved
