"""M11/M12 残留收口：告警按范围隐藏、有效技能只能查自己。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from mailbus.bootstrap.main import create_app
from mailbus.bootstrap.settings import Settings


def _client(tmp_path) -> TestClient:
    return TestClient(create_app(Settings(data_dir=tmp_path)))


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bootstrap(client: TestClient) -> str:
    response = client.post(
        "/api/identity/bootstrap/super-admin", json={"display_name": "超级管理员"}
    )
    assert response.status_code == 201, response.text
    return response.json()["token"]


def _plain_token(client: TestClient, admin: dict[str, str]) -> str:
    invite = client.post(
        "/api/employees/invite", json={"display_name": "普通员工"}, headers=admin
    )
    assert invite.status_code in (200, 201), invite.text
    accepted = client.post(
        "/api/invites/accept",
        json={"invite_code": invite.json()["invite_code"]},
    )
    assert accepted.status_code == 201, accepted.text
    return accepted.json()["token"]


def test_alerts_hidden_for_non_privileged(tmp_path):
    with _client(tmp_path) as client:
        admin = _headers(_bootstrap(client))
        user = _headers(_plain_token(client, admin))

        assert client.get("/api/alerts", headers=admin).status_code == 200
        body = client.get("/api/alerts", headers=user)
        # B7 起告警需要 log_read 或 console_admin，普通员工 403
        assert body.status_code == 403, body.text


def test_effective_skills_restricted_to_self(tmp_path):
    with _client(tmp_path) as client:
        admin = _headers(_bootstrap(client))
        admin_id = client.get("/api/identity/me", headers=admin).json()["employee_id"]
        user = _headers(_plain_token(client, admin))
        user_id = client.get("/api/identity/me", headers=user).json()["employee_id"]

        # 普通员工查他人员工 → 403
        denied = client.get(
            "/api/skills/effective",
            params={"target_type": "employee", "target_id": admin_id},
            headers=user,
        )
        assert denied.status_code == 403, denied.text

        # 查自己 → 200
        allowed = client.get(
            "/api/skills/effective",
            params={"target_type": "employee", "target_id": user_id},
            headers=user,
        )
        assert allowed.status_code == 200, allowed.text

        # 管理员（ALL）可跨查
        admin_view = client.get(
            "/api/skills/effective",
            params={"target_type": "employee", "target_id": user_id},
            headers=admin,
        )
        assert admin_view.status_code == 200, admin_view.text


def test_effective_skills_rejects_other_agent(tmp_path):
    with _client(tmp_path) as client:
        admin = _headers(_bootstrap(client))
        user = _headers(_plain_token(client, admin))

        denied = client.get(
            "/api/skills/effective",
            params={"target_type": "agent", "target_id": "agent_unknown"},
            headers=user,
        )
        assert denied.status_code == 403, denied.text
