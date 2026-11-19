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

        team = client.post("/api/org/teams", json={"name": "平台研发部"}, headers=headers)
        assert team.status_code == 201, team.text
        team_id = team.json()["team_id"]

        position = client.post(
            "/api/org/positions",
            json={"name": "后端工程师", "capabilities": ["message_send"]},
            headers=headers,
        )
        assert position.status_code == 201, position.text
        position_id = position.json()["position_id"]
        assert position.json()["capabilities"] == ["message_send"]

        seats = client.get("/api/org/seats", headers=headers).json()
        assert len(seats) == 22
        seat_id = seats[0]["seat_id"]

        assigned = client.patch(
            f"/api/org/seats/{seat_id}",
            json={"team_id": team_id, "position_id": position_id, "rotation": 90},
            headers=headers,
        )
        assert assigned.status_code == 200, assigned.text
        assert assigned.json()["rotation"] == 90
        assert assigned.json()["team_id"] == team_id

        # 没有 org_manage 的员工不能创建团队
        staff = client.post(
            "/api/identity/staff",
            json={"display_name": "小王", "account_type": "human", "seat_id": seat_id},
        )
        assert staff.status_code == 201, staff.text
        employee_id = staff.json()["employee"]["employee_id"]
        # 入职落座即按工位岗位补齐能力
        assert "message_send" in staff.json()["employee"]["capabilities"]
        client.post(
            f"/api/identity/staff/{employee_id}/review",
            json={"approved": True},
            headers=headers,
        )
        staff_token = client.post(
            f"/api/identity/staff/{employee_id}/activate", headers=headers
        ).json()["token"]
        denied = client.post(
            "/api/org/teams", json={"name": "越权团队"}, headers=_headers(staff_token)
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
        # 员工档案缺失归属时回退到工位覆盖
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
        }

        # 工位调换：只能由 org_manage 角色操作，并按新工位岗位补齐能力
        target_seat = seats[1]["seat_id"]
        second = client.post(
            "/api/org/positions",
            json={"name": "调度员", "capabilities": ["task_create"]},
            headers=headers,
        ).json()
        client.patch(
            f"/api/org/seats/{target_seat}",
            json={"position_id": second["position_id"]},
            headers=headers,
        )
        moved = client.patch(
            f"/api/identity/staff/{employee_id}/seat",
            json={"seat_id": target_seat},
            headers=headers,
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["seat_id"] == target_seat
        assert {"message_send", "task_create"} <= set(moved.json()["capabilities"])

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
            "team",
            "status",
            "task",
            "agent_name",
            "agent_framework",
            "task_state",
            "current_node",
            "node_state",
            "progress_done",
            "progress_total",
        }

        # 离职自动释放工位：座位回到空闲，且可被新员工重新分配
        dismissed = client.post(
            f"/api/identity/staff/{employee_id}/deregister",
            json={"reason": "离职"},
            headers=headers,
        )
        assert dismissed.status_code == 200, dismissed.text
        assert dismissed.json()["status"] == "deregistered"
        assert dismissed.json()["seat_id"] is None

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

        newcomer = client.post(
            "/api/identity/staff", json={"display_name": "接任者", "account_type": "human"}
        ).json()["employee"]["employee_id"]
        client.post(
            f"/api/identity/staff/{newcomer}/review",
            json={"approved": True},
            headers=headers,
        )
        client.post(f"/api/identity/staff/{newcomer}/activate", headers=headers)
        reseated = client.patch(
            f"/api/identity/staff/{newcomer}/seat",
            json={"seat_id": target_seat},
            headers=headers,
        )
        assert reseated.status_code == 200, reseated.text
        assert reseated.json()["seat_id"] == target_seat
