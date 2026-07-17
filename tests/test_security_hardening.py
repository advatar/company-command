from pathlib import Path

from fastapi.testclient import TestClient

from comcmd.config import Settings
from comcmd.server.app import create_app


COMPANIES = Path(__file__).resolve().parents[1] / "companies"


def test_http_control_plane_requires_bearer_token_when_configured():
    client = TestClient(create_app(Settings(api_token="secret"),
                                    companies_dir=str(COMPANIES)))
    assert client.get("/health").status_code == 200
    assert client.get("/companies").status_code == 401
    assert client.get("/companies", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/companies", headers={"Authorization": "Bearer secret"}).status_code == 200


def test_approval_request_contains_immutable_operation_payload():
    from comcmd.pack import build_runner, load_pack

    pack = COMPANIES / "auto-steam"
    runner = build_runner(load_pack(pack)).runner
    task = runner.start("ship-title", {"title": "Bound title"})
    significant = task.waiting_on["approval"]["significant"]
    assert significant["args"]["operation"]["inputs"] == {"title": "Bound title"}
    assert "upstream" in significant["args"]["operation"]
