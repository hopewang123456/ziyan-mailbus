"""安全回归：能力授予上界（C3）与员工列表数据范围（H6）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from mailbus.bootstrap.main import create_app
from mailbus.bootstrap.settings import Settings


def _client(tmp_path) -> TestClient:
    return TestClient(create_app(Settings(data_dir=tmp_path)))


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bootstrap(client: TestClient) -> dict:
    resp = client.post(
        "/api/identity/bootstrap/super-admin", json={"display_name": "超管"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _make_manager(client: TestClient, admin_token: str) -> str:
    """管理员签发邀请→员工激活→提拔为管理者，返回管理者 token。"""
    invite = client.post(
        "/api/identity/invites", json={"account_type": "human"}, headers=_h(admin_token)
    ).json()
    employee = client.post(
        "/api/identity/staff",
        json={"display_name": "经理", "account_type": "human", "invite_code": invite["invite_code"]},
    ).json()
    employee_id = employee["employee"]["employee_id"]
    client.patch(
        f"/api/identity/staff/{employee_id}/manager",
        json={"enabled": True},
        headers=_h(admin_token),
    )
    return employee["token"]


def test_manager_cannot_issue_all_or_wider_scope_invite(tmp_path):
    with _client(tmp_path) as client:
        admin_token = _bootstrap(client)["token"]
        manager_token = _make_manager(client, admin_token)

        # 授予 ALL：禁止
        denied = client.post(
            "/api/identity/invites",
            json={"account_type": "human", "capabilities": ["*"]},
            headers=_h(manager_token),
        )
        assert denied.status_code == 403
        assert denied.json()["error_code"] == "permission_denied"

        # 授予超出自身范围的能力（管理者无 system_config）：禁止
        denied2 = client.post(
            "/api/identity/invites",
            json={"account_type": "human", "capabilities": ["system_config"]},
            headers=_h(manager_token),
        )
        assert denied2.status_code == 403

        # 授予高于自身的数据范围（管理者默认 self，申请 team）：禁止
        denied3 = client.post(
            "/api/identity/invites",
            json={"account_type": "human", "data_scope": "team"},
            headers=_h(manager_token),
        )
        assert denied3.status_code == 403

        # 管理者授予自己拥有的能力（如 message_send）+ self 范围：允许
        ok = client.post(
            "/api/identity/invites",
            json={"account_type": "human", "capabilities": ["message_send"]},
            headers=_h(manager_token),
        )
        assert ok.status_code == 201, ok.text


def test_manager_cannot_create_or_assign_god_position(tmp_path):
    with _client(tmp_path) as client:
        admin_token = _bootstrap(client)["token"]
        manager_token = _make_manager(client, admin_token)

        # 管理者建带 * 的岗位：禁止
        denied = client.post(
            "/api/org/positions",
            json={"name": "上帝岗", "capabilities": ["*"]},
            headers=_h(manager_token),
        )
        assert denied.status_code == 403

        # 超管建立 * 岗位
        god = client.post(
            "/api/org/positions",
            json={"name": "上帝岗", "capabilities": ["*"]},
            headers=_h(admin_token),
        ).json()
        god_id = god["position_id"]

        seat_id = client.get("/api/org/seats", headers=_h(admin_token)).json()[0]["seat_id"]

        # 管理者把 * 岗位分配给工位：禁止
        denied_assign = client.patch(
            f"/api/org/seats/{seat_id}",
            json={"position_id": god_id},
            headers=_h(manager_token),
        )
        assert denied_assign.status_code == 403

        # 超管分配：允许
        ok = client.patch(
            f"/api/org/seats/{seat_id}",
            json={"position_id": god_id},
            headers=_h(admin_token),
        )
        assert ok.status_code == 200, ok.text


def test_list_staff_respects_data_scope(tmp_path):
    with _client(tmp_path) as client:
        admin_token = _bootstrap(client)["token"]
        team_a = client.post(
            "/api/org/teams", json={"name": "A 队"}, headers=_h(admin_token)
        ).json()["team_id"]
        team_b = client.post(
            "/api/org/teams", json={"name": "B 队"}, headers=_h(admin_token)
        ).json()["team_id"]

        # A 队一名持 employee_invite、self 范围的员工
        inv_a = client.post(
            "/api/identity/invites",
            json={
                "account_type": "human",
                "team_id": team_a,
                "capabilities": ["employee_invite"],
                "data_scope": "self",
            },
            headers=_h(admin_token),
        ).json()
        emp_a = client.post(
            "/api/identity/staff",
            json={
                "display_name": "甲",
                "account_type": "human",
                "invite_code": inv_a["invite_code"],
            },
        ).json()
        a_id = emp_a["employee"]["employee_id"]

        # B 队一名普通员工
        inv_b = client.post(
            "/api/identity/invites",
            json={"account_type": "human", "team_id": team_b, "data_scope": "self"},
            headers=_h(admin_token),
        ).json()
        emp_b = client.post(
            "/api/identity/staff",
            json={
                "display_name": "乙",
                "account_type": "human",
                "invite_code": inv_b["invite_code"],
            },
        ).json()
        b_id = emp_b["employee"]["employee_id"]

        # self 范围：只能看到自己
        rows = client.get("/api/identity/staff?status=all", headers=_h(emp_a["token"])).json()
        seen = {row["employee_id"] for row in rows}
        assert seen == {a_id}
        assert b_id not in seen

        # 超管（global）：能看到全部
        admin_rows = client.get(
            "/api/identity/staff?status=all", headers=_h(admin_token)
        ).json()
        admin_seen = {row["employee_id"] for row in admin_rows}
        assert {a_id, b_id} <= admin_seen
