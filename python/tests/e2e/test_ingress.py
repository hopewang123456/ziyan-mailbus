"""B5/B6 端到端：A2A 用 Agent token 自校验，MCP 仍走能力鉴权。"""

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
    invite = client.post(
        "/api/employees/invite",
        json={"display_name": "员工丙"},
        headers=admin_headers,
    )
    assert invite.status_code in (200, 201), invite.text
    accepted = client.post(
        "/api/invites/accept",
        json={"invite_code": invite.json()["invite_code"]},
    )
    assert accepted.status_code == 201, accepted.text
    return accepted.json()["token"]


def test_a2a_uses_agent_token_and_mcp_uses_capability(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        admin_headers = _headers(_bootstrap(client))
        staff_headers = _headers(_staff_token(client, admin_headers))

        # A2A 单入口只认 Agent token：缺失或非 Agent token 均 401
        a2a_missing = client.post("/api/a2a/messages", json={"type": "heartbeat"})
        a2a_staff = client.post(
            "/api/a2a/messages", json={"type": "heartbeat"}, headers=staff_headers
        )
        assert a2a_missing.status_code == 401
        assert a2a_staff.status_code == 401

        # MCP 仍按登录账号能力鉴权
        mcp_denied = client.post(
            "/api/mcp/messages", json={"body": "越权拉取"}, headers=staff_headers
        )
        assert mcp_denied.status_code == 403
        assert mcp_denied.json()["error_code"] == "permission_denied"

        mcp_ok = client.post(
            "/api/mcp/messages", json={"body": "MCP 成功"}, headers=admin_headers
        )
        assert mcp_ok.status_code == 201, mcp_ok.text

        pulled = client.get("/api/mcp/pull", headers=admin_headers)
        assert pulled.status_code == 200
        assert client.get("/api/overview", headers=admin_headers).json()[
            "messages_total"
        ] == 1
