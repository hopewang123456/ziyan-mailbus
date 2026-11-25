"""B2 组织域契约：员工目录、邀请生命周期、职位/角色/团队、软删除与 410。"""

from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from mailbus.bootstrap.main import create_app
from mailbus.bootstrap.settings import Settings


def _client(tmp_path) -> TestClient:
    return TestClient(create_app(Settings(data_dir=tmp_path)))


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bootstrap(client: TestClient) -> str:
    response = client.post(
        "/api/identity/bootstrap/super-admin", json={"display_name": "超管"}
    )
    assert response.status_code == 201, response.text
    return response.json()["token"]


def _new_employee(client: TestClient, token: str, name: str = "员工") -> dict:
    invite = client.post(
        "/api/employees/invite",
        json={"display_name": name, "permissions": ["message_send"]},
        headers=_h(token),
    )
    assert invite.status_code == 200, invite.text
    accepted = client.post(
        "/api/invites/accept", json={"invite_code": invite.json()["invite_code"]}
    )
    assert accepted.status_code == 201, accepted.text
    return accepted.json()


def test_employee_crud_permissions_and_options(tmp_path):
    with _client(tmp_path) as client:
        admin = _bootstrap(client)
        created = _new_employee(client, admin, "小张")
        employee = created["employee"]
        employee_id = employee["employee_id"]
        assert employee["permissions"] == ["message_send"]
        assert created["token"]

        listed = client.get("/api/employees", headers=_h(admin)).json()
        assert listed["total"] == 2
        assert {item["employee_id"] for item in listed["items"]} >= {employee_id}
        assert client.get(
            "/api/employees?type=agent", headers=_h(admin)
        ).json()["total"] == 0

        detail = client.get(f"/api/employees/{employee_id}", headers=_h(admin))
        assert detail.status_code == 200
        assert set(detail.json()) == {
            "employee_id", "display_name", "account_type", "status", "team_id",
            "position_id", "seat_id", "agent_id", "agent_name", "agent_framework",
            "permissions", "data_scope", "file_scope", "endpoint",
            "endpoint_approved", "last_heartbeat",
        }

        renamed = client.patch(
            f"/api/employees/{employee_id}",
            json={"display_name": "小张改", "data_scope": "team"},
            headers=_h(admin),
        )
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["display_name"] == "小张改"
        assert renamed.json()["data_scope"] == "team"

        perms = client.put(
            f"/api/employees/{employee_id}/permissions",
            json={"permissions": ["message_send", "task_create"]},
            headers=_h(admin),
        )
        assert perms.status_code == 200
        assert perms.json()["permissions"] == ["message_send", "task_create"]
        assert client.get(
            f"/api/employees/{employee_id}/permissions", headers=_h(admin)
        ).json()["permissions"] == ["message_send", "task_create"]

        skills = client.put(
            f"/api/employees/{employee_id}/capabilities",
            json={"capabilities": ["python", "review"]},
            headers=_h(admin),
        )
        assert skills.status_code == 200
        assert skills.json()["capabilities"] == ["python", "review"]

        options = client.get("/api/options/employees", headers=_h(admin)).json()
        assert options["total"] == 2
        assert set(options["items"][0]) == {"option_id", "label", "enabled"}


def test_invite_revoke_resend_and_gone(tmp_path):
    with _client(tmp_path) as client:
        admin = _bootstrap(client)
        invite = client.post(
            "/api/employees/invite",
            json={"display_name": "受邀者", "permissions": ["message_send"]},
            headers=_h(admin),
        ).json()
        invite_id = invite["invite_id"]
        assert invite["invite_code"]

        revoked = client.post(f"/api/invites/{invite_id}/revoke", headers=_h(admin))
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["revoked_at"]
        assert revoked.json()["invite_code"] is None

        gone = client.post(
            "/api/invites/accept", json={"invite_code": invite["invite_code"]}
        )
        assert gone.status_code == 410, gone.text

        resent = client.post(f"/api/invites/{invite_id}/resend", headers=_h(admin))
        assert resent.status_code == 200, resent.text
        assert resent.json()["invite_code"] != invite["invite_code"]

        old_gone = client.post(
            "/api/invites/accept", json={"invite_code": invite["invite_code"]}
        )
        assert old_gone.status_code == 410

        accepted = client.post(
            "/api/invites/accept", json={"invite_code": resent.json()["invite_code"]}
        )
        assert accepted.status_code == 201, accepted.text

        reused = client.post(
            "/api/invites/accept", json={"invite_code": resent.json()["invite_code"]}
        )
        assert reused.status_code == 410

        missing = client.post(
            "/api/invites/accept", json={"invite_code": "inv-missing"}
        )
        assert missing.status_code == 404


def test_positions_roles_teams_and_seat_conflicts(tmp_path):
    with _client(tmp_path) as client:
        admin = _bootstrap(client)
        alice = _new_employee(client, admin, "Alice")["employee"]["employee_id"]
        bob = _new_employee(client, admin, "Bob")["employee"]["employee_id"]

        position = client.post(
            "/api/positions",
            json={"name": "后端", "capabilities": ["python"]},
            headers=_h(admin),
        )
        assert position.status_code == 201, position.text
        position_id = position.json()["position_id"]

        role = client.post(
            "/api/roles",
            json={"name": "评审", "capabilities": ["review"]},
            headers=_h(admin),
        )
        assert role.status_code == 201, role.text
        role_id = role.json()["role_id"]

        bound = client.put(
            f"/api/positions/{position_id}/roles",
            json={"ids": [role_id]},
            headers=_h(admin),
        )
        assert bound.status_code == 200
        assert bound.json()["role_ids"] == [role_id]

        assigned = client.put(
            f"/api/positions/{position_id}/employees",
            json={"ids": [alice]},
            headers=_h(admin),
        )
        assert assigned.status_code == 200
        assert client.get(
            f"/api/employees/{alice}", headers=_h(admin)
        ).json()["position_id"] == position_id

        blocked = client.delete(f"/api/roles/{role_id}", headers=_h(admin))
        assert blocked.status_code == 409

        team = client.post(
            "/api/teams", json={"name": "平台"}, headers=_h(admin)
        )
        assert team.status_code == 201, team.text
        team_id = team.json()["team_id"]
        updated = client.patch(
            f"/api/teams/{team_id}",
            json={"name": "平台组", "leader_employee_id": alice},
            headers=_h(admin),
        )
        assert updated.status_code == 200
        assert updated.json()["leader_employee_id"] == alice

        seat = client.get(f"/api/teams/{team_id}/seats", headers=_h(admin)).json()
        assert seat["total"] == 0

        first = client.put(
            "/api/seats/f1-bullpen-s1/assign",
            json={"employee_id": alice, "team_id": team_id, "position_id": position_id},
            headers=_h(admin),
        )
        assert first.status_code == 200, first.text
        assert first.json()["employee_id"] == alice
        seats = client.get(f"/api/teams/{team_id}/seats", headers=_h(admin)).json()
        assert seats["total"] == 1

        conflict = client.put(
            "/api/seats/f1-bullpen-s1/assign",
            json={"employee_id": bob, "team_id": team_id},
            headers=_h(admin),
        )
        assert conflict.status_code == 409

        released = client.put(
            "/api/seats/f1-bullpen-s1/assign",
            json={"team_id": team_id},
            headers=_h(admin),
        )
        assert released.status_code == 200
        assert released.json()["employee_id"] is None


def test_soft_delete_and_active_run_conflict(tmp_path):
    with _client(tmp_path) as client:
        admin = _bootstrap(client)
        first = _new_employee(client, admin, "待删")["employee"]["employee_id"]
        second = _new_employee(client, admin, "忙")["employee"]["employee_id"]

        with sqlite3.connect(tmp_path / "mailbus.db") as conn:
            conn.execute(
                "INSERT INTO task_node_runs (run_id, task_id, node_id, attempt_no,"
                " state, assigned_employee_id) VALUES (?, ?, ?, 1, 'running', ?)",
                ("run-1", "task-1", "node-1", second),
            )

        busy = client.delete(f"/api/employees/{second}", headers=_h(admin))
        assert busy.status_code == 409, busy.text

        ok = client.delete(f"/api/employees/{first}", headers=_h(admin))
        assert ok.status_code == 204
        assert client.get(f"/api/employees/{first}", headers=_h(admin)).status_code == 404
        listed = client.get("/api/employees", headers=_h(admin)).json()
        assert first not in {item["employee_id"] for item in listed["items"]}

        with sqlite3.connect(tmp_path / "mailbus.db") as conn:
            conn.execute("DELETE FROM task_node_runs WHERE run_id = 'run-1'")
        assert client.delete(
            f"/api/employees/{second}", headers=_h(admin)
        ).status_code == 204


def test_regular_staff_is_denied_org_writes(tmp_path):
    with _client(tmp_path) as client:
        admin = _bootstrap(client)
        staff = _new_employee(client, admin, "普通员工")
        token = staff["token"]
        employee_id = staff["employee"]["employee_id"]

        for response in (
            client.post(
                "/api/positions", json={"name": "X"}, headers=_h(token)
            ),
            client.patch(
                f"/api/employees/{employee_id}",
                json={"display_name": "越权"},
                headers=_h(token),
            ),
            client.put(
                f"/api/employees/{employee_id}/permissions",
                json={"permissions": ["console_admin"]},
                headers=_h(token),
            ),
            client.post(
                "/api/teams", json={"name": "X"}, headers=_h(token)
            ),
        ):
            assert response.status_code == 403, response.text
