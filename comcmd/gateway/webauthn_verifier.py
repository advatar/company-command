"""WebAuthn approval verifier — the real Phase 1 ApprovalVerifier.

Verifies a WebAuthn *authentication* assertion produced by an approver's passkey
and returns the authenticated principal. This is the cryptographic proof of
consent that replaces iProov for routine approvals.

Security properties enforced (STRATEGY.md §7.1, OWASP transaction auth):
  - challenge binding: the assertion signs the exact challenge the gateway
    issued for one specific action digest (1:1, anti-TOCTOU);
  - origin + RP id binding: phishing resistance;
  - user verification required: biometric/PIN activation actually occurred;
  - sign-count monotonicity: cloned-authenticator detection;
  - single-use is enforced by the approval store (challenge retired on use).

Base64url decode helpers accept the standard WebAuthn JSON wire format.
"""

from __future__ import annotations

import base64

import webauthn
from webauthn.helpers import exceptions as wa_exc

from comcmd.gateway.enrollment import CredentialStore
from comcmd.gateway.verifier import Decision


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


class WebAuthnVerifier:
    """ApprovalVerifier that authenticates an approver via WebAuthn.

    ``verify`` returns a Decision whose ``principal`` is the enrolled approver on
    success. The gateway uses ``principal`` to enforce approver eligibility and
    distinct-person quorum.
    """

    def __init__(self, credentials: CredentialStore, *, rp_id: str, origin: str,
                 require_user_verification: bool = True):
        self._creds = credentials
        self._rp_id = rp_id
        self._origin = origin
        self._require_uv = require_user_verification

    def verify(self, *, approval_request: dict, assertion: dict | None) -> Decision:
        if assertion is None:
            return Decision(False, "no assertion presented")

        try:
            raw_id = _b64url_decode(assertion["rawId"])
        except Exception as exc:  # malformed assertion → fail closed
            return Decision(False, f"malformed assertion: {exc}")

        cred = self._creds.get(raw_id)
        if cred is None:
            return Decision(False, "unknown credential (not enrolled)")

        expected_challenge = approval_request.get("_challenge")
        if not isinstance(expected_challenge, (bytes, bytearray)):
            return Decision(False, "approval request has no bound challenge")

        try:
            va = webauthn.verify_authentication_response(
                credential=assertion,
                expected_challenge=bytes(expected_challenge),
                expected_rp_id=self._rp_id,
                expected_origin=self._origin,
                credential_public_key=cred.public_key,
                credential_current_sign_count=cred.sign_count,
                require_user_verification=self._require_uv,
            )
        except wa_exc.InvalidAuthenticationResponse as exc:
            return Decision(False, f"assertion rejected: {exc}")
        except Exception as exc:  # never approve on an unexpected error
            return Decision(False, f"verification error: {exc}")

        # Advance sign count (clone/replay detection across ceremonies).
        self._creds.update_sign_count(raw_id, va.new_sign_count)
        return Decision(True, "webauthn verified", principal=cred.principal)
