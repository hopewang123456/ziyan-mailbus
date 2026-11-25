"""B1 端到端：引导向导 + 员工全生命周期 + 越权与一次性邀请。"""

from __future__ import annotations

import sqlite3
from datetime import timedelta

from fastapi.testclient import TestClient

from mailbus.bootstrap.main import create_app
from mailbus.bootstrap.settings import Settings


def _client(tmp_path) -> TestClient:
    return TestClient(create_app(Settings(data_dir=tmp_path)))


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bootstrap(client: TestClient) -> dict:
    response = client.post(
        "/api/identity/bootstrap/super-admin", json={"display_name": "超级管理员"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _hire(
    client: TestClient, admin_headers: dict[str, str], name: str, **invite_fields
) -> dict:
    invite = client.post(
        "/api/employees/invite",
        json={"display_name": name, **invite_fields},
        headers=admin_headers,
    )
    assert invite.status_code in (200, 201), invite.text
    accepted = client.post(
        "/api/invites/accept",
        json={"invite_code": invite.json()["invite_code"], "display_name": name},
    )
    assert accepted.status_code == 201, accepted.text
    return {"invite": invite.json(), **accepted.json()}


def _position(client: TestClient, headers: dict[str, str], name: str = "Agent 岗") -> str:
    response = client.post("/api/positions", json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["position_id"]


def _register_agent(
    client: TestClient,
    headers: dict[str, str],
    name: str,
    position_id: str,
    endpoint: str | None = None,
) -> dict:
    invite = client.post(
        "/api/agent-invites",
        json={"employee_name": name, "position_id": position_id},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    payload: dict = {"invite_code": invite.json()["invite_code"], "name": name}
    if endpoint is not None:
        payload["endpoint"] = endpoint
    registered = client.post("/api/agents/register", json=payload)
    assert registered.status_code == 201, registered.text
    return {"invite": invite.json(), **registered.json()}


def test_bootstrap_wizard_is_ordered_and_idempotent(tmp_path):
    with _client(tmp_path) as client:
        status = client.get("/api/identity/bootstrap").json()
        assert status["completed"] is False
        assert [step["step"] for step in status["steps"]] == [
            "super_admin",
            "model_config",
            "first_team",
        ]

        admin = _bootstrap(client)
        assert admin["employee"]["status"] == "active"
        assert admin["employee"]["permissions"] == ["*"]
        token = admin["token"]

        assert (
            client.post("/api/identity/bootstrap/super-admin", json={"display_name": "重复"}).status_code
            == 409
        )
        assert (
            client.post(
                "/api/identity/bootstrap/model-config",
                json={"provider": "deepseek", "model": "deepseek-v4"},
            ).status_code
            == 401
        )

        configured = client.post(
            "/api/identity/bootstrap/model-config",
            json={"provider": "deepseek", "model": "deepseek-v4", "api_base": "https://api.example"},
            headers=_headers(token),
        )
        assert configured.status_code == 200, configured.text
        assert configured.json()["completed"] is False

        team = client.post(
            "/api/identity/bootstrap/team", json={"name": "交付一组"}, headers=_headers(token)
        )
        assert team.status_code == 200, team.text
        assert team.json()["team_id"].startswith("team_")
        assert client.get("/api/identity/bootstrap").json()["completed"] is True


def test_staff_status_filter(tmp_path):
    with _client(tmp_path) as client:
        admin = _bootstrap(client)
        admin_id = admin["employee"]["employee_id"]
        admin_headers = _headers(admin["token"])

        # B8：邀请即激活，不再有 pending 生命周期。
        first_id = _hire(client, admin_headers, "在职甲")["employee"]["employee_id"]
        second_id = _hire(client, admin_headers, "在职乙")["employee"]["employee_id"]

        def ids(status: str) -> set[str]:
            response = client.get(
                f"/api/identity/staff?status={status}", headers=admin_headers
            )
            assert response.status_code == 200, response.text
            return {item["employee_id"] for item in response.json()}

        assert ids("pending") == set()
        assert ids("active") == {first_id, second_id, admin_id}
        assert {first_id, second_id, admin_id} <= ids("all")
        assert (
            client.get("/api/identity/staff?status=bogus", headers=admin_headers).status_code
            == 422
        )


def test_staff_lifecycle_end_to_end(tmp_path):
    with _client(tmp_path) as client:
        admin_token = _bootstrap(client)["token"]
        admin_headers = _headers(admin_token)
        team_id = client.post(
            "/api/teams", json={"name": "交付一组"}, headers=admin_headers
        ).json()["team_id"]

        # Agent 走新域：邀请 → 自助注册，注册即激活。
        position_id = _position(client, admin_headers)
        agent = _register_agent(client, admin_headers, "小助手", position_id)
        assert agent["token"]
        agent_employee = client.get(
            f"/api/employees/{agent['employee_id']}", headers=admin_headers
        ).json()
        assert agent_employee["status"] == "active"
        assert agent_employee["account_type"] == "agent"
        assert agent_employee["agent_id"] == agent["agent_id"]

        reused_agent = client.post(
            "/api/agents/register",
            json={"invite_code": agent["invite"]["invite_code"], "name": "冒用者"},
        )
        assert reused_agent.status_code == 409

        missing_agent = client.post(
            "/api/agents/register", json={"invite_code": "mbreg_missing", "name": "无"}
        )
        assert missing_agent.status_code == 404

        # 真人走邀请 → 接受，接受即激活并签发 token。
        hired = _hire(client, admin_headers, "小王", team_id=team_id)
        employee_id = hired["employee"]["employee_id"]
        assert hired["employee"]["status"] == "active"
        assert hired["employee"]["team_id"] == team_id
        staff_token = hired["token"]

        reused = client.post(
            "/api/invites/accept",
            json={"invite_code": hired["invite"]["invite_code"]},
        )
        assert reused.status_code == 410
        assert reused.json()["error_code"] == "invite_gone"

        # 新员工没有 employee_invite 能力，签发邀请应被拒
        denied = client.post(
            "/api/employees/invite",
            json={"display_name": "越权"},
            headers=_headers(staff_token),
        )
        assert denied.status_code == 403
        assert denied.json()["error_code"] == "permission_denied"

        # 普通员工只能给自己上报心跳
        admin_id = client.get(
            "/api/identity/me", headers=admin_headers
        ).json()["employee_id"]
        other = client.post(
            f"/api/identity/staff/{admin_id}/heartbeat", headers=_headers(staff_token)
        )
        assert other.status_code == 403

        # 超管可代任意员工续心跳（演示/运维保活）
        proxy = client.post(
            f"/api/identity/staff/{employee_id}/heartbeat", headers=admin_headers
        )
        assert proxy.status_code == 200, proxy.text
        assert proxy.json()["status"] == "active"

        beat = client.post(
            f"/api/identity/staff/{employee_id}/heartbeat", headers=_headers(staff_token)
        )
        assert beat.status_code == 200, beat.text
        assert beat.json()["status"] == "active"

        # 软删除员工：204，并立即吊销会话
        dismissed = client.delete(
            f"/api/employees/{employee_id}", headers=admin_headers
        )
        assert dismissed.status_code == 204, dismissed.text
        assert client.get(
            "/api/identity/me", headers=_headers(staff_token)
        ).status_code == 401
        assert client.get("/api/identity/me").status_code == 401


def test_manager_and_endpoint_toggles(tmp_path):
    with _client(tmp_path) as client:
        admin_headers = _headers(_bootstrap(client)["token"])
        position_id = _position(client, admin_headers)
        registered = _register_agent(
            client, admin_headers, "小助手", position_id,
            endpoint="http://127.0.0.1:9001",
        )
        agent_id = registered["agent_id"]
        assert registered["endpoint_review_status"] == "pending"

        approved = client.post(
            f"/api/agents/{agent_id}/endpoint/approve", headers=admin_headers
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["endpoint"] == "http://127.0.0.1:9001"
        assert approved.json()["endpoint_review_status"] == "approved"

        employee_id = _hire(
            client, admin_headers, "管理者"
        )["employee"]["employee_id"]

        promoted = client.put(
            f"/api/employees/{employee_id}/permissions",
            json={"permissions": ["console_admin"]},
            headers=admin_headers,
        )
        assert promoted.status_code == 200, promoted.text
        capabilities = set(promoted.json()["permissions"])
        assert "console_admin" in capabilities
        assert "system_config" not in capabilities
        assert "employee_remove" not in capabilities

        demoted = client.put(
            f"/api/employees/{employee_id}/permissions",
            json={"permissions": []},
            headers=admin_headers,
        )
        assert demoted.status_code == 200, demoted.text
        assert "console_admin" not in demoted.json()["permissions"]


def test_admin_backfills_agent_endpoint(tmp_path):
    with _client(tmp_path) as client:
        admin_headers = _headers(_bootstrap(client)["token"])
        position_id = _position(client, admin_headers)

        target = _register_agent(
            client, admin_headers, "补录对象", position_id,
            endpoint="http://127.0.0.1:9100",
        )
        path = f"/api/agents/{target['agent_id']}/endpoint"

        detail = client.get(f"/api/agents/{target['agent_id']}", headers=admin_headers)
        assert detail.status_code == 200, detail.text
        assert detail.json()["endpoint"] is None
        assert detail.json()["pending_endpoint"] == "http://127.0.0.1:9100"
        assert detail.json()["endpoint_review_status"] == "pending"

        backfilled = client.post(f"{path}/approve", headers=admin_headers)
        assert backfilled.status_code == 200, backfilled.text
        assert backfilled.json()["endpoint"] == "http://127.0.0.1:9100"
        assert backfilled.json()["endpoint_review_status"] == "approved"

        # 新上报地址进入待审；拒绝后不落地为正式 endpoint。
        rejected_target = _register_agent(
            client, admin_headers, "拒绝对象", position_id,
            endpoint="http://127.0.0.1:9101",
        )
        rejected = client.post(
            f"/api/agents/{rejected_target['agent_id']}/endpoint/reject",
            headers=admin_headers,
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["endpoint"] is None
        assert rejected.json()["endpoint_review_status"] == "rejected"

        assert (
            client.post(
                "/api/agents/agent_missing/endpoint/approve", headers=admin_headers
            ).status_code
            == 404
        )

        worker_token = _hire(client, admin_headers, "普通员工")["token"]
        denied = client.post(
            f"{path}/approve", headers=_headers(worker_token)
        )
        assert denied.status_code == 403


def test_employee_detail_and_option_scope(tmp_path):
    with _client(tmp_path) as client:
        admin_headers = _headers(_bootstrap(client)["token"])
        first = _hire(client, admin_headers, "甲")
        second = _hire(client, admin_headers, "乙")
        first_id = first["employee"]["employee_id"]
        second_id = second["employee"]["employee_id"]
        first_headers = _headers(first["token"])

        assert (
            client.get(f"/api/employees/{first_id}", headers=admin_headers).status_code
            == 200
        )
        assert (
            client.get(f"/api/employees/{first_id}", headers=first_headers).status_code
            == 200
        )

        # 详情读取目前为登录即可；数据范围保护由脱敏选项接口承载：
        # self 范围员工只能看到自己。
        options = client.get("/api/options/employees", headers=first_headers).json()
        assert {item["option_id"] for item in options["items"]} == {first_id}
        assert second_id not in {item["option_id"] for item in options["items"]}

        admin_options = client.get(
            "/api/options/employees", headers=admin_headers
        ).json()
        assert {item["option_id"] for item in admin_options["items"]} == {
            first_id,
            second_id,
            _bootstrap_id(client, admin_headers),
        }


def _bootstrap_id(client: TestClient, headers: dict[str, str]) -> str:
    return client.get("/api/identity/me", headers=headers).json()["employee_id"]


def test_logout_revokes_current_session(tmp_path):
    with _client(tmp_path) as client:
        token = _bootstrap(client)["token"]
        headers = _headers(token)
        assert client.get("/api/identity/me", headers=headers).status_code == 200

        logged_out = client.post("/api/identity/logout", headers=headers)
        assert logged_out.status_code == 204
        assert client.get("/api/identity/me", headers=headers).status_code == 401


def test_heartbeat_timeout_marks_offline(tmp_path):
    with _client(tmp_path) as client:
        admin = _bootstrap(client)
        admin_headers = _headers(admin["token"])
        hired = _hire(client, admin_headers, "小王")
        staff_token = hired["token"]

        container = client.app.state.container
        cutoff = container.clock.now() + timedelta(seconds=1)
        assert container.identity.staff.mark_stale_offline(cutoff) >= 1
        me = client.get("/api/identity/me", headers=_headers(staff_token)).json()
        assert me["status"] == "offline"


def test_accept_issues_timed_session(tmp_path):
    """接受邀请签发限时会话（B8 起无永久会话入口）。"""
    with _client(tmp_path) as client:
        admin_headers = _headers(_bootstrap(client)["token"])
        hired = _hire(client, admin_headers, "限时")
        employee_id = hired["employee"]["employee_id"]

        assert client.get(
            "/api/identity/me", headers=_headers(hired["token"])
        ).status_code == 200

        connection = sqlite3.connect(tmp_path / "mailbus.db")
        try:
            rows = dict(
                connection.execute(
                    "select employee_id, expires_at from identity_sessions"
                ).fetchall()
            )
        finally:
            connection.close()
        assert rows[employee_id] is not None
