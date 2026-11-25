"""B7：Agent 邀请码状态校验顺序与明文只回显一次。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mailbus.bootstrap.main import create_app
from mailbus.bootstrap.settings import Settings


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as test_client:
        yield test_client


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _invite(client: TestClient, headers, position_id: str) -> dict:
    response = client.post(
        "/api/agent-invites",
        json={
            "employee_name": "执行 Agent",
            "position_id": position_id,
            "capabilities": ["ops"],
            "permissions": ["message_send", "result_submit"],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_agent_invite_validation_order(client):
    response = client.post(
        "/api/identity/bootstrap/super-admin", json={"display_name": "超级管理员"}
    )
    headers = _headers(response.json()["token"])
    position = client.post("/api/positions", json={"name": "Agent 岗"}, headers=headers)
    position_id = position.json()["position_id"]

    invite = _invite(client, headers, position_id)
    code = invite["invite_code"]
    assert code

    # 列表不回显完整邀请码；长期有效（expires_at 为空）
    listed = client.get("/api/agent-invites", headers=headers)
    assert listed.status_code == 200, listed.text
    item = listed.json()["items"][0]
    assert item["invite_id"] == invite["invite_id"]
    assert not item.get("invite_code")
    assert item["expires_at"] is None

    registered = client.post(
        "/api/agents/register",
        json={"invite_code": code, "name": "执行 Agent",
              "endpoint": "http://127.0.0.1:7890/a2a"},
    )
    assert registered.status_code == 201, registered.text

    # 已使用 → 409；已撤销 → 410；不存在 → 404
    reused = client.post(
        "/api/agents/register", json={"invite_code": code, "name": "重复注册"}
    )
    assert reused.status_code == 409

    second = _invite(client, headers, position_id)
    revoked = client.post(
        f"/api/agent-invites/{second['invite_id']}/revoke", headers=headers
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["revoked_at"]
    gone = client.post(
        "/api/agents/register", json={"invite_code": second["invite_code"], "name": "撤销"}
    )
    assert gone.status_code == 410

    missing = client.post(
        "/api/agents/register", json={"invite_code": "mbreg_missing", "name": "不存在"}
    )
    assert missing.status_code == 404
