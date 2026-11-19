"""B1 端到端：引导向导 + 员工全生命周期 + 越权与一次性邀请。"""

from __future__ import annotations

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
        assert admin["employee"]["capabilities"] == ["*"]
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

        pending_id = client.post(
            "/api/identity/staff", json={"display_name": "待审", "account_type": "human"}
        ).json()["employee"]["employee_id"]
        active_id = client.post(
            "/api/identity/staff", json={"display_name": "在职", "account_type": "human"}
        ).json()["employee"]["employee_id"]
        client.post(
            f"/api/identity/staff/{active_id}/review",
            json={"approved": True},
            headers=admin_headers,
        )
        client.post(f"/api/identity/staff/{active_id}/activate", headers=admin_headers)

        def ids(status: str) -> set[str]:
            response = client.get(
                f"/api/identity/staff?status={status}", headers=admin_headers
            )
            assert response.status_code == 200, response.text
            return {item["employee_id"] for item in response.json()}

        assert ids("pending") == {pending_id}
        assert ids("active") == {active_id, admin_id}
        assert {pending_id, active_id, admin_id} <= ids("all")
        assert (
            client.get("/api/identity/staff?status=bogus", headers=admin_headers).status_code
            == 422
        )


def test_staff_lifecycle_end_to_end(tmp_path):
    with _client(tmp_path) as client:
        admin_token = _bootstrap(client)["token"]
        admin_headers = _headers(admin_token)
        team_id = client.post(
            "/api/identity/bootstrap/team", json={"name": "交付一组"}, headers=admin_headers
        ).json()["team_id"]

        invite = client.post(
            "/api/identity/invites",
            json={
                "account_type": "agent",
                "team_id": team_id,
                "capabilities": ["message_send"],
                "data_scope": "team",
            },
            headers=admin_headers,
        )
        assert invite.status_code == 201, invite.text
        invite_code = invite.json()["invite_code"]

        agent = client.post(
            "/api/identity/staff",
            json={
                "display_name": "小助手",
                "account_type": "agent",
                "invite_code": invite_code,
                "endpoint": "http://127.0.0.1:9001",
            },
        )
        assert agent.status_code == 201, agent.text
        assert agent.json()["employee"]["status"] == "active"
        assert agent.json()["token"]

        reused = client.post(
            "/api/identity/staff",
            json={"display_name": "冒用者", "account_type": "agent", "invite_code": invite_code},
        )
        assert reused.status_code == 400
        assert reused.json()["error_code"] == "invite_invalid"

        applied = client.post(
            "/api/identity/staff", json={"display_name": "小王", "account_type": "human"}
        )
        assert applied.status_code == 201, applied.text
        employee_id = applied.json()["employee"]["employee_id"]
        assert applied.json()["employee"]["status"] == "pending"
        assert applied.json()["token"] is None

        assert employee_id in [e["employee_id"] for e in client.get(
            "/api/identity/staff", headers=admin_headers
        ).json()]

        reviewed = client.post(
            f"/api/identity/staff/{employee_id}/review",
            json={"approved": True},
            headers=admin_headers,
        )
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["status"] == "pending"

        activated = client.post(
            f"/api/identity/staff/{employee_id}/activate", headers=admin_headers
        )
        assert activated.status_code == 200, activated.text
        assert activated.json()["employee"]["status"] == "active"
        staff_token = activated.json()["token"]

        # 新员工没有 employee_invite 能力，签发邀请应被拒
        denied = client.post(
            "/api/identity/invites",
            json={"account_type": "agent"},
            headers=_headers(staff_token),
        )
        assert denied.status_code == 403
        assert denied.json()["error_code"] == "permission_denied"

        # 只能给自己上报心跳
        other = client.post(
            f"/api/identity/staff/{employee_id}/heartbeat", headers=admin_headers
        )
        assert other.status_code == 403

        beat = client.post(
            f"/api/identity/staff/{employee_id}/heartbeat", headers=_headers(staff_token)
        )
        assert beat.status_code == 200, beat.text
        assert beat.json()["status"] == "active"

        dismissed = client.post(
            f"/api/identity/staff/{employee_id}/deregister",
            json={"reason": "离职"},
            headers=admin_headers,
        )
        assert dismissed.status_code == 200, dismissed.text
        assert dismissed.json()["status"] == "deregistered"

        # 注销后会话立即失效
        assert client.get("/api/identity/me", headers=_headers(staff_token)).status_code == 401
        assert client.get("/api/identity/me").status_code == 401


def test_manager_and_endpoint_toggles(tmp_path):
    with _client(tmp_path) as client:
        admin = _bootstrap(client)
        admin_headers = _headers(admin["token"])
        invite = client.post(
            "/api/identity/invites",
            json={"account_type": "agent", "capabilities": ["message_send"]},
            headers=admin_headers,
        ).json()
        agent = client.post(
            "/api/identity/staff",
            json={
                "display_name": "小助手",
                "account_type": "agent",
                "invite_code": invite["invite_code"],
                "endpoint": "http://127.0.0.1:9001",
            },
        ).json()["employee"]
        employee_id = agent["employee_id"]
        assert agent["endpoint_approved"] is False

        approved = client.patch(
            f"/api/identity/staff/{employee_id}/endpoint",
            json={"approved": True},
            headers=admin_headers,
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["endpoint_approved"] is True

        promoted = client.patch(
            f"/api/identity/staff/{employee_id}/manager",
            json={"enabled": True},
            headers=admin_headers,
        )
        assert promoted.status_code == 200, promoted.text
        capabilities = set(promoted.json()["capabilities"])
        assert "console_admin" in capabilities
        assert "system_config" not in capabilities
        assert "employee_remove" not in capabilities

        demoted = client.patch(
            f"/api/identity/staff/{employee_id}/manager",
            json={"enabled": False},
            headers=admin_headers,
        )
        assert demoted.status_code == 200, demoted.text
        assert "console_admin" not in demoted.json()["capabilities"]


def test_staff_detail_self_and_permission(tmp_path):
    with _client(tmp_path) as client:
        admin_headers = _headers(_bootstrap(client)["token"])

        def activate(name: str) -> tuple[str, str]:
            applied = client.post(
                "/api/identity/staff",
                json={"display_name": name, "account_type": "human"},
            )
            employee_id = applied.json()["employee"]["employee_id"]
            client.post(
                f"/api/identity/staff/{employee_id}/review",
                json={"approved": True},
                headers=admin_headers,
            )
            token = client.post(
                f"/api/identity/staff/{employee_id}/activate",
                headers=admin_headers,
            ).json()["token"]
            return employee_id, token

        first_id, first_token = activate("甲")
        second_id, _ = activate("乙")

        assert (
            client.get(f"/api/identity/staff/{first_id}", headers=admin_headers).status_code
            == 200
        )
        assert (
            client.get(
                f"/api/identity/staff/{first_id}", headers=_headers(first_token)
            ).status_code
            == 200
        )
        assert (
            client.get(
                f"/api/identity/staff/{second_id}", headers=_headers(first_token)
            ).status_code
            == 403
        )


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
        employee_id = client.post(
            "/api/identity/staff", json={"display_name": "小王", "account_type": "human"}
        ).json()["employee"]["employee_id"]
        client.post(
            f"/api/identity/staff/{employee_id}/review",
            json={"approved": True},
            headers=admin_headers,
        )
        staff_token = client.post(
            f"/api/identity/staff/{employee_id}/activate", headers=admin_headers
        ).json()["token"]

        container = client.app.state.container
        cutoff = container.clock.now() + timedelta(seconds=1)
        assert container.identity.staff.mark_stale_offline(cutoff) >= 1
        me = client.get("/api/identity/me", headers=_headers(staff_token)).json()
        assert me["status"] == "offline"
