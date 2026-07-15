"""A minimal software WebAuthn authenticator for tests.

Produces registration and authentication responses in the WebAuthn JSON wire
format that py_webauthn verifies, with the User Verified (UV) flag set — which
soft-webauthn does not do, and which Acme requires for approvals. Uses ES256
(P-256) over the `cryptography` library only (no extra deps).

This is test scaffolding, not production code: it stands in for a real
passkey/authenticator on the operator's device.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

FLAG_UP = 0x01
FLAG_UV = 0x04
FLAG_AT = 0x40


def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


class SoftAuthenticator:
    def __init__(self, rp_id: str, origin: str, *, user_verified: bool = True):
        self.rp_id = rp_id
        self.origin = origin
        self.user_verified = user_verified
        self._key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self._sign_count = 0

    # -- COSE / authData helpers --------------------------------------------

    def _cose_key(self) -> bytes:
        nums = self._key.public_key().public_numbers()
        x = nums.x.to_bytes(32, "big")
        y = nums.y.to_bytes(32, "big")
        return cbor2.dumps({1: 2, 3: -7, -1: 1, -2: x, -3: y})

    def _flags(self, *, attested: bool) -> int:
        f = FLAG_UP
        if self.user_verified:
            f |= FLAG_UV
        if attested:
            f |= FLAG_AT
        return f

    def _auth_data(self, *, attested: bool) -> bytes:
        rp_id_hash = hashlib.sha256(self.rp_id.encode()).digest()
        data = rp_id_hash + bytes([self._flags(attested=attested)])
        data += self._sign_count.to_bytes(4, "big")
        if attested:
            aaguid = b"\x00" * 16
            cred = self._cose_key()
            data += aaguid + len(self.credential_id).to_bytes(2, "big")
            data += self.credential_id + cred
        return data

    def _client_data(self, ceremony: str, challenge: bytes) -> bytes:
        return json.dumps({
            "type": ceremony,
            "challenge": b64url(challenge),
            "origin": self.origin,
            "crossOrigin": False,
        }, separators=(",", ":")).encode()

    # -- ceremonies ----------------------------------------------------------

    def register(self, challenge: bytes) -> dict:
        client_data = self._client_data("webauthn.create", challenge)
        att_obj = cbor2.dumps({
            "fmt": "none", "attStmt": {},
            "authData": self._auth_data(attested=True),
        })
        return {
            "id": b64url(self.credential_id),
            "rawId": b64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(client_data),
                "attestationObject": b64url(att_obj),
            },
            "clientExtensionResults": {},
        }

    def authenticate(self, challenge: bytes) -> dict:
        self._sign_count += 1
        auth_data = self._auth_data(attested=False)
        client_data = self._client_data("webauthn.get", challenge)
        signed = auth_data + hashlib.sha256(client_data).digest()
        signature = self._key.sign(signed, ec.ECDSA(hashes.SHA256()))
        return {
            "id": b64url(self.credential_id),
            "rawId": b64url(self.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64url(client_data),
                "authenticatorData": b64url(auth_data),
                "signature": b64url(signature),
                "userHandle": None,
            },
            "clientExtensionResults": {},
        }
