"""B6 端到端：A2A / MCP / file_bus 三入口共用同一鉴权。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from mailbus.bootstrap.main import create_app
from mailbus.bootstrap.settings import Settings


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bootstrap(client: TestClient) -> str:
    response = client.post(
        "/api/identity/bootstrap/super-admin", json={"display_name": "超级管理员"}
    )
    assert response.status_code == 201, response.text
    return response.json()["token"]


def _staff_token(client: TestClient, admin_headers: dict[str, str]) -> str:
    applied = client.post(
        "/api/identity/staff", json={"display_name": "员工丙", "account_type": "human"}
    )
    employee_id = applied.json()["employee"]["employee_id"]
    client.post(
        f"/api/identity/staff/{employee_id}/review",
        json={"approved": True},
        headers=admin_headers,
    )
    activated = client.post(
        f"/api/identity/staff/{employee_id}/activate", headers=admin_headers
    )
    assert activated.status_code == 200, activated.text
    return activated.json()["token"]


def test_a2a_and_mcp_share_the_same_authorizer(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        admin_headers = _headers(_bootstrap(client))
        staff_headers = _headers(_staff_token(client, admin_headers))

        a2a_denied = client.post(
            "/api/a2a/messages", json={"body": "越权直推"}, headers=staff_headers
        )
        mcp_denied = client.post(
            "/api/mcp/messages", json={"body": "越权拉取"}, headers=staff_headers
        )
        assert a2a_denied.status_code == 403
        assert mcp_denied.status_code == 403
        assert a2a_denied.json()["error_code"] == mcp_denied.json()["error_code"]

        a2a_ok = client.post(
            "/api/a2a/messages", json={"body": "直推成功"}, headers=admin_headers
        )
        mcp_ok = client.post(
            "/api/mcp/messages", json={"body": "MCP 成功"}, headers=admin_headers
        )
        assert a2a_ok.status_code == 201, a2a_ok.text
        assert mcp_ok.status_code == 201, mcp_ok.text

        pulled = client.get("/api/mcp/pull", headers=admin_headers)
        assert pulled.status_code == 200
        assert client.get("/api/overview", headers=admin_headers).json()[
            "messages_total"
        ] == 2
