"""HTTP API end-to-end: start a task, enroll a passkey, approve over HTTP.

Uses FastAPI's in-process TestClient and the software authenticator to drive the
full WebAuthn ceremony against the real service — no browser, no network.
"""

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from comcmd.config import Settings
from comcmd.server.app import create_app
from tests.support.authenticator import SoftAuthenticator

COMPANIES = Path(__file__).resolve().parents[1] / "companies"
RP_ID = "localhost"
ORIGIN = "https://localhost"


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


@pytest.fixture
def client():
    app = create_app(Settings(rp_id=RP_ID, rp_origin=ORIGIN),
                     companies_dir=str(COMPANIES))
    return TestClient(app)


def test_health_lists_companies(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["durable"] is False
    assert "auto-steam" in body["companies"]


def test_full_governed_lifecycle_over_http(client):
    dev = SoftAuthenticator(RP_ID, ORIGIN)

    # 1. start a task -> parks at the human gate
    r = client.post("/companies/auto-steam/tasks", json={"workflow": "ship-title"})
    assert r.status_code == 200
    task = r.json()
    assert task["state"] == "WAITING_FOR_HUMAN"
    assert task["artifacts"]["market"]["greenlit"] is True
    digest = task["waiting_on"]["intent_digest"]
    task_id = task["task_id"]

    # 2. it shows up in the approval inbox
    inbox = client.get("/companies/auto-steam/approvals").json()
    assert any(a["intent_digest"] == digest for a in inbox)

    # 3. enroll a passkey (WebAuthn registration ceremony over HTTP)
    opts = client.post("/companies/auto-steam/credentials/options",
                       json={"principal": "human:studio-lead"}).json()
    reg_challenge = _b64url_decode(opts["publicKey"]["challenge"])
    reg = dev.register(reg_challenge)
    r = client.post("/companies/auto-steam/credentials",
                    json={"principal": "human:studio-lead", "credential": reg})
    assert r.status_code == 200 and r.json()["enrolled"] is True

    # 4. authenticate the approval (WebAuthn assertion over HTTP)
    ao = client.post(f"/companies/auto-steam/approvals/{digest}/options").json()
    assertion = dev.authenticate(_b64url_decode(ao["challenge"]))
    r = client.post("/companies/auto-steam/approvals/submit",
                    json={"task_id": task_id, "workflow": "ship-title",
                          "step": "release", "assertion": assertion})
    assert r.status_code == 200
    assert r.json()["state"] == "SUCCEEDED"

    # 5. audit log shows the publish executed exactly once
    events = client.get("/companies/auto-steam/events").json()
    executed = [e for e in events if e["type"] == "execution_receipt"
                and e["payload"].get("executed") is True]
    assert len(executed) == 1

    # 6. task status reconstructs from the ledger
    status = client.get(f"/companies/auto-steam/tasks/{task_id}").json()
    assert status["state"] == "SUCCEEDED" and status["chain_valid"] is True


def test_eval_endpoint(client):
    r = client.post("/companies/triage-demo/eval",
                    json={"baseline": "triage-single", "variant": "triage-panel"})
    assert r.status_code == 200
    body = r.json()
    assert body["promote"] is True
    assert body["variant"]["success_rate"] > body["baseline"]["success_rate"]


def test_unknown_company_404(client):
    assert client.get("/companies/nope/approvals").status_code == 404
