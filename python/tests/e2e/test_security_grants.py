"""安全回归：能力授予上界（C3）与员工列表数据范围（H6）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from mailbus.bootstrap.main import create_app
from mailbus.bootstrap.settings import Settings

# 管理者能力包（不含 system_config / employee_remove / agent_deregister / ALL）
_MANAGER_PERMISSIONS = [
    "console_admin",
    "employee_invite",
    "org_manage",
    "hitl_request",
    "hitl_resolve",
    "task_create",
    "task_dispatch",
    "workflow_create",
    "workflow_modify",
    "message_send",
    "log_read",
]


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


def _hire(
    client: TestClient, admin_token: str, name: str, **invite_fields
) -> tuple[str, str]:
    invite = client.post(
        "/api/employees/invite",
        json={"display_name": name, **invite_fields},
        headers=_h(admin_token),
    )
    assert invite.status_code in (200, 201), invite.text
    accepted = client.post(
        "/api/invites/accept",
        json={"invite_code": invite.json()["invite_code"], "display_name": name},
    )
    assert accepted.status_code == 201, accepted.text
    body = accepted.json()
    return body["employee"]["employee_id"], body["token"]


def _make_manager(client: TestClient, admin_token: str) -> str:
    """经邀请创建员工，再由超管授予管理者能力包，返回管理者 token。"""
    employee_id, token = _hire(client, admin_token, "经理")
    promoted = client.put(
        f"/api/employees/{employee_id}/permissions",
        json={"permissions": _MANAGER_PERMISSIONS},
        headers=_h(admin_token),
    )
    assert promoted.status_code == 200, promoted.text
    return token


def test_manager_cannot_issue_all_or_wider_scope_invite(tmp_path):
    with _client(tmp_path) as client:
        admin_token = _bootstrap(client)["token"]
        manager_token = _make_manager(client, admin_token)

        # 授予 ALL：禁止
        denied = client.post(
            "/api/employees/invite",
            json={"display_name": "越权", "permissions": ["*"]},
            headers=_h(manager_token),
        )
        assert denied.status_code == 403
        assert denied.json()["error_code"] == "permission_denied"

        # 授予超出自身范围的能力（管理者无 system_config）：禁止
        denied2 = client.post(
            "/api/employees/invite",
            json={"display_name": "越权", "permissions": ["system_config"]},
            headers=_h(manager_token),
        )
        assert denied2.status_code == 403

        # 授予高于自身的数据范围（管理者默认 self，申请 team）：禁止
        denied3 = client.post(
            "/api/employees/invite",
            json={"display_name": "越权", "data_scope": "team"},
            headers=_h(manager_token),
        )
        assert denied3.status_code == 403

        # 管理者授予自己拥有的能力（如 message_send）+ self 范围：允许
        ok = client.post(
            "/api/employees/invite",
            json={"display_name": "新同事", "permissions": ["message_send"]},
            headers=_h(manager_token),
        )
        assert ok.status_code in (200, 201), ok.text


def test_manager_cannot_grant_permissions_beyond_self(tmp_path):
    with _client(tmp_path) as client:
        admin_token = _bootstrap(client)["token"]
        manager_token = _make_manager(client, admin_token)

        # 岗位 capabilities 是业务技能标签：管理者可自由登记
        position = client.post(
            "/api/positions",
            json={"name": "上帝岗", "capabilities": ["*"]},
            headers=_h(manager_token),
        )
        assert position.status_code == 201, position.text

        employee_id, _ = _hire(client, admin_token, "普通员工")

        # 管理者授予 ALL：禁止
        denied = client.put(
            f"/api/employees/{employee_id}/permissions",
            json={"permissions": ["*"]},
            headers=_h(manager_token),
        )
        assert denied.status_code == 403

        # 授予自身拥有的普通权限：允许
        ok = client.put(
            f"/api/employees/{employee_id}/permissions",
            json={"permissions": ["message_send"]},
            headers=_h(manager_token),
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["permissions"] == ["message_send"]


def test_list_staff_respects_data_scope(tmp_path):
    with _client(tmp_path) as client:
        admin_token = _bootstrap(client)["token"]
        team_a = client.post(
            "/api/teams", json={"name": "A 队"}, headers=_h(admin_token)
        ).json()["team_id"]
        team_b = client.post(
            "/api/teams", json={"name": "B 队"}, headers=_h(admin_token)
        ).json()["team_id"]

        # A 队一名持 employee_invite、self 范围的员工
        a_id, a_token = _hire(
            client,
            admin_token,
            "甲",
            team_id=team_a,
            permissions=["employee_invite"],
            data_scope="self",
        )

        # B 队一名普通员工
        b_id, _ = _hire(client, admin_token, "乙", team_id=team_b, data_scope="self")

        # self 范围：只能看到自己
        rows = client.get(
            "/api/identity/staff?status=all", headers=_h(a_token)
        ).json()
        seen = {row["employee_id"] for row in rows}
        assert seen == {a_id}
        assert b_id not in seen

        # 超管（global）：能看到全部
        admin_rows = client.get(
            "/api/identity/staff?status=all", headers=_h(admin_token)
        ).json()
        admin_seen = {row["employee_id"] for row in admin_rows}
        assert {a_id, b_id} <= admin_seen
