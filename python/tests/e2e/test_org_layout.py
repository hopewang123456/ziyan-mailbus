"""B2 端到端：组织 CRUD 与孪生布局逐字段对齐 types.ts。"""

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


def _hire(
    client: TestClient, headers: dict[str, str], name: str, **invite_fields
) -> dict:
    invite = client.post(
        "/api/employees/invite",
        json={"display_name": name, **invite_fields},
        headers=headers,
    )
    assert invite.status_code in (200, 201), invite.text
    accepted = client.post(
        "/api/invites/accept",
        json={"invite_code": invite.json()["invite_code"], "display_name": name},
    )
    assert accepted.status_code == 201, accepted.text
    return accepted.json()


def _seat_ids(client: TestClient, headers: dict[str, str]) -> list[str]:
    layout = client.get("/api/layout", headers=headers).json()
    return [
        seat["seat_id"]
        for floor in layout["floors"]
        for room in floor["rooms"]
        for seat in room["seats"]
    ]


def _assign(client, headers, seat_id: str, **payload):
    return client.put(
        f"/api/seats/{seat_id}/assign", json=payload, headers=headers
    )


def _teams(client, headers) -> dict[str, dict]:
    rows = client.get("/api/teams", headers=headers).json()["items"]
    return {row["team_id"]: row for row in rows}


def _positions(client, headers) -> dict[str, dict]:
    rows = client.get("/api/positions", headers=headers).json()["items"]
    return {row["position_id"]: row for row in rows}


def test_layout_matches_twin_contract(tmp_path):
    with _client(tmp_path) as client:
        token = _bootstrap(client)
        headers = _headers(token)

        layout = client.get("/api/layout", headers=headers)
        assert layout.status_code == 200, layout.text
        site = layout.json()
        assert set(site) == {"site_id", "name", "org_name", "floors"}
        assert site["site_id"] == "site-hq"

        floor = site["floors"][0]
        assert set(floor) == {"floor_id", "name", "level", "rooms"}
        room = floor["rooms"][0]
        assert set(room) == {"room_id", "name", "kind", "x", "y", "w", "h", "seats"}
        assert room["kind"] in {"reception", "bullpen", "focus", "meeting", "lounge"}

        seat = room["seats"][0]
        assert set(seat) == {"seat_id", "x", "y", "rotation", "agent"}
        assert seat["agent"] is None


def test_org_teams_positions_and_seat_assignment(tmp_path):
    with _client(tmp_path) as client:
        token = _bootstrap(client)
        headers = _headers(token)

        team = client.post("/api/teams", json={"name": "平台研发部"}, headers=headers)
        assert team.status_code == 201, team.text
        team_id = team.json()["team_id"]

        position = client.post(
            "/api/positions",
            json={"name": "后端工程师", "capabilities": ["message_send"]},
            headers=headers,
        )
        assert position.status_code == 201, position.text
        position_id = position.json()["position_id"]
        assert position.json()["capabilities"] == ["message_send"]
        assert position.json()["role_ids"] == []

        seats = _seat_ids(client, headers)
        assert len(seats) == 22
        seat_id = seats[0]

        assigned = _assign(
            client, headers, seat_id,
            team_id=team_id, position_id=position_id,
        )
        assert assigned.status_code == 200, assigned.text
        assert assigned.json()["team_id"] == team_id
        assert assigned.json()["position_id"] == position_id

        # 没有 org_manage 的员工不能创建团队
        staff = _hire(
            client, headers, "小王", team_id=team_id, position_id=position_id
        )
        employee_id = staff["employee"]["employee_id"]
        # 岗位 capabilities 是业务技能标签，不再授予登录权限
        assert "message_send" not in staff["employee"]["permissions"]
        placed = _assign(
            client, headers, seat_id,
            employee_id=employee_id, team_id=team_id, position_id=position_id,
        )
        assert placed.status_code == 200, placed.text
        denied = client.post(
            "/api/teams", json={"name": "越权团队"}, headers=_headers(staff["token"])
        )
        assert denied.status_code == 403

        # 员工落座后布局出现 agent 投影
        layout = client.get("/api/layout", headers=headers).json()
        flat = [
            seat
            for floor in layout["floors"]
            for room in floor["rooms"]
            for seat in room["seats"]
        ]
        occupied = next(item for item in flat if item["seat_id"] == seat_id)
        assert occupied["agent"]["agent_id"] == employee_id
        assert occupied["agent"]["status"] == "online"
        assert occupied["agent"]["team"] == "平台研发部"
        assert occupied["agent"]["position"] == "后端工程师"
        assert set(occupied["agent"]) == {
            "agent_id",
            "display_name",
            "position",
            "team",
            "status",
            "task",
            "last_heartbeat",
            "bound_agent_id",
            "agent_name",
            "agent_framework",
            "task_id",
            "task_state",
            "current_node",
            "node_state",
            "progress_done",
            "progress_total",
            "pair_id",
            "partner_name",
        }

        # 工位调换：只能由 org_manage 角色操作，并按新工位岗位补齐能力
        target_seat = seats[1]
        second = client.post(
            "/api/positions",
            json={"name": "调度员", "capabilities": ["task_create"]},
            headers=headers,
        ).json()
        _assign(client, headers, target_seat, position_id=second["position_id"])
        moved = _assign(client, headers, target_seat, employee_id=employee_id)
        assert moved.status_code == 200, moved.text
        assert moved.json()["employee_id"] == employee_id
        detail = client.get(
            f"/api/employees/{employee_id}", headers=headers
        ).json()
        assert detail["seat_id"] == target_seat
        assert "task_create" not in set(detail["permissions"])

        # 公开大屏：无需鉴权，且不暴露 agent_id / last_heartbeat
        public = client.get("/api/public/layout")
        assert public.status_code == 200, public.text
        public_seats = [
            seat
            for floor in public.json()["floors"]
            for room in floor["rooms"]
            for seat in room["seats"]
        ]
        public_agent = next(
            item["agent"] for item in public_seats if item["seat_id"] == target_seat
        )
        assert set(public_agent) == {
            "display_name",
            "position",
            "status",
            "task",
            "agent_name",
            "agent_framework",
            "task_state",
            "current_node",
            "node_state",
            "progress_done",
            "progress_total",
            "pair_id",
            "partner_name",
        }

        # 离职自动释放工位：座位回到空闲，且可被新员工重新分配
        dismissed = client.delete(
            f"/api/employees/{employee_id}", headers=headers
        )
        assert dismissed.status_code == 204, dismissed.text

        freed = client.get("/api/layout", headers=headers).json()
        freed_seats = [
            seat
            for floor in freed["floors"]
            for room in floor["rooms"]
            for seat in room["seats"]
        ]
        assert next(
            item for item in freed_seats if item["seat_id"] == target_seat
        )["agent"] is None

        newcomer = _hire(client, headers, "接任者")["employee"]["employee_id"]
        reseated = _assign(client, headers, target_seat, employee_id=newcomer)
        assert reseated.status_code == 200, reseated.text
        assert client.get(
            f"/api/employees/{newcomer}", headers=headers
        ).json()["seat_id"] == target_seat


def test_team_and_position_delete_guards_seat_references(tmp_path):
    with _client(tmp_path) as client:
        token = _bootstrap(client)
        headers = _headers(token)

        team = client.post(
            "/api/teams", json={"name": "临时团队"}, headers=headers
        ).json()
        position = client.post(
            "/api/positions", json={"name": "临时岗位"}, headers=headers
        ).json()
        seat_id = _seat_ids(client, headers)[0]
        _assign(
            client, headers, seat_id,
            team_id=team["team_id"], position_id=position["position_id"],
        )

        assert (
            client.delete(
                f"/api/teams/{team['team_id']}", headers=headers
            ).status_code
            == 409
        )
        assert (
            client.delete(
                f"/api/positions/{position['position_id']}", headers=headers
            ).status_code
            == 409
        )

        # 显式 null 清除工位归属，随后才能删除
        cleared = _assign(
            client, headers, seat_id, team_id=None, position_id=None
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["team_id"] is None
        assert cleared.json()["position_id"] is None

        deleted_team = client.delete(
            f"/api/teams/{team['team_id']}", headers=headers
        )
        assert deleted_team.status_code == 204
        deleted_position = client.delete(
            f"/api/positions/{position['position_id']}", headers=headers
        )
        assert deleted_position.status_code == 204
        assert (
            client.delete(
                f"/api/teams/{team['team_id']}", headers=headers
            ).status_code
            == 404
        )

        staff_token = _hire(client, headers, "普通员工")["token"]
        extra = client.post(
            "/api/teams", json={"name": "越权团队"}, headers=headers
        ).json()
        denied = client.delete(
            f"/api/teams/{extra['team_id']}", headers=_headers(staff_token)
        )
        assert denied.status_code == 403

        # 员工引用同样阻止删除，软删除后才能删除
        locked_team = client.post(
            "/api/teams", json={"name": "有人的团队"}, headers=headers
        ).json()
        locked_position = client.post(
            "/api/positions", json={"name": "有人的岗位"}, headers=headers
        ).json()
        # 归属只能经邀请带入：邀请决定团队/岗位
        member = _hire(
            client, headers, "在册成员",
            team_id=locked_team["team_id"],
            position_id=locked_position["position_id"],
        )["employee"]["employee_id"]

        assert (
            client.delete(
                f"/api/teams/{locked_team['team_id']}", headers=headers
            ).status_code
            == 409
        )
        assert (
            client.delete(
                f"/api/positions/{locked_position['position_id']}", headers=headers
            ).status_code
            == 409
        )

        # 停用（deregistered）后不再阻止删除
        assert (
            client.patch(
                f"/api/employees/{member}",
                json={"enabled": False},
                headers=headers,
            ).status_code
            == 200
        )
        assert (
            client.delete(
                f"/api/teams/{locked_team['team_id']}", headers=headers
            ).status_code
            == 204
        )
        assert (
            client.delete(
                f"/api/positions/{locked_position['position_id']}", headers=headers
            ).status_code
            == 204
        )


def test_team_delete_after_soft_deleted_employee(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))
        team = client.post(
            "/api/teams", json={"name": "软删除团队"}, headers=headers
        ).json()
        member = _hire(
            client, headers, "已删成员", team_id=team["team_id"]
        )["employee"]["employee_id"]

        assert (
            client.delete(f"/api/employees/{member}", headers=headers).status_code
            == 204
        )
        assert (
            client.delete(f"/api/teams/{team['team_id']}", headers=headers).status_code
            == 204
        )


def _staff_token(client: TestClient, headers: dict[str, str], name: str) -> str:
    """创建一名普通员工（无 org_manage），返回 token。"""
    return _hire(client, headers, name)["token"]


def test_org_teams_list_contract(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))

        empty = client.get("/api/teams", headers=headers)
        assert empty.status_code == 200, empty.text
        assert empty.json()["items"] == []
        assert empty.json()["total"] == 0

        created = [
            client.post(
                "/api/teams", json={"name": n}, headers=headers
            ).json()
            for n in ("平台研发部", "产品部")
        ]

        listed = client.get("/api/teams", headers=headers)
        assert listed.status_code == 200, listed.text
        rows = listed.json()["items"]
        assert {row["team_id"] for row in rows} == {c["team_id"] for c in created}
        for row in rows:
            assert set(row) == {
                "team_id", "name", "leader_employee_id", "created_at",
            }

        # 读端点无需 org_manage
        staff_headers = _headers(_staff_token(client, headers, "只读员工"))
        assert client.get("/api/teams", headers=staff_headers).status_code == 200


def test_org_teams_list_requires_auth(tmp_path):
    with _client(tmp_path) as client:
        assert client.get("/api/teams").status_code == 401


def test_org_positions_list_contract(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))

        empty = client.get("/api/positions", headers=headers)
        assert empty.status_code == 200, empty.text
        assert empty.json()["items"] == []

        with_caps = client.post(
            "/api/positions",
            json={"name": "后端工程师", "capabilities": ["message_send"]},
            headers=headers,
        )
        assert with_caps.status_code == 201, with_caps.text
        no_caps = client.post(
            "/api/positions", json={"name": "实习生"}, headers=headers
        )
        assert no_caps.status_code == 201, no_caps.text

        rows = _positions(client, headers)
        assert set(rows) == {with_caps.json()["position_id"], no_caps.json()["position_id"]}
        for row in rows.values():
            assert set(row) == {
                "position_id", "name", "capabilities", "role_ids", "created_at",
            }
            assert isinstance(row["capabilities"], list)
            assert isinstance(row["role_ids"], list)
        assert rows[with_caps.json()["position_id"]]["capabilities"] == ["message_send"]
        assert rows[no_caps.json()["position_id"]]["capabilities"] == []

        staff_headers = _headers(_staff_token(client, headers, "只读员工"))
        assert (
            client.get("/api/positions", headers=staff_headers).status_code == 200
        )


def test_org_positions_list_requires_auth(tmp_path):
    with _client(tmp_path) as client:
        assert client.get("/api/positions").status_code == 401
