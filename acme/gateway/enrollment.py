"""Credential enrollment — who may approve, and with which passkey.

A principal (e.g. ``human:board``) enrolls one or more WebAuthn credentials. The
approval verifier checks an assertion against the enrolled public key. The
private key never leaves the authenticator; Acme stores only the public key,
credential id, and a monotonically increasing sign count (clone detection).

This is the authentication side of STRATEGY.md §7: authenticating the approver.
Registration *trust* (attestation/AAGUID policy) is deferred — Phase 1 accepts
"none" attestation for enrollment, which is standard for first-party passkeys.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import webauthn


@dataclass
class EnrolledCredential:
    principal: str
    credential_id: bytes
    public_key: bytes           # COSE-encoded
    sign_count: int = 0


class CredentialStore:
    def __init__(self) -> None:
        self._by_id: dict[bytes, EnrolledCredential] = {}
        self._by_principal: dict[str, list[EnrolledCredential]] = {}

    def enroll_verified(self, principal: str, *, credential_id: bytes,
                        public_key: bytes, sign_count: int = 0) -> EnrolledCredential:
        cred = EnrolledCredential(principal, credential_id, public_key, sign_count)
        self._by_id[credential_id] = cred
        self._by_principal.setdefault(principal, []).append(cred)
        return cred

    def enroll_registration(self, principal: str, *, credential: dict,
                            expected_challenge: bytes, rp_id: str,
                            origin: str) -> EnrolledCredential:
        """Verify a WebAuthn registration response and store the credential."""
        vr = webauthn.verify_registration_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
        )
        return self.enroll_verified(
            principal,
            credential_id=vr.credential_id,
            public_key=vr.credential_public_key,
            sign_count=vr.sign_count,
        )

    def get(self, credential_id: bytes) -> EnrolledCredential | None:
        return self._by_id.get(credential_id)

    def principals(self) -> list[str]:
        return list(self._by_principal.keys())

    def update_sign_count(self, credential_id: bytes, new_count: int) -> None:
        cred = self._by_id.get(credential_id)
        if cred is not None:
            cred.sign_count = new_count
