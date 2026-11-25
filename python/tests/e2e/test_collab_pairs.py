"""结对与协同消息/任务端到端：创建、消息投影、公开读取与结束。"""

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


def _hire(client: TestClient, admin: dict[str, str], name: str) -> tuple[str, str]:
    invite = client.post(
        "/api/employees/invite", json={"display_name": name}, headers=admin
    )
    assert invite.status_code in (200, 201), invite.text
    accepted = client.post(
        "/api/invites/accept",
        json={"invite_code": invite.json()["invite_code"], "display_name": name},
    )
    assert accepted.status_code == 201, accepted.text
    body = accepted.json()
    return body["employee"]["employee_id"], body["token"]


def test_pair_lifecycle_and_collab_projection(tmp_path):
    with _client(tmp_path) as client:
        admin = _headers(_bootstrap(client))
        me = client.get("/api/identity/me", headers=admin).json()["employee_id"]
        partner_id, partner_token = _hire(client, admin, "搭档")
        colleague = _headers(partner_token)

        created = client.post(
            "/api/collab/pairs", json={"partner_id": partner_id}, headers=admin
        )
        assert created.status_code == 201, created.text
        pair = created.json()
        pair_id = pair["pair_id"]
        assert pair["initiator_id"] == me
        assert pair["partner_id"] == partner_id
        assert pair["state"] == "active"

        duplicate = client.post(
            "/api/collab/pairs", json={"partner_id": partner_id}, headers=admin
        )
        assert duplicate.status_code == 409

        assert (
            client.post(
                "/api/collab/pairs", json={"partner_id": me}, headers=admin
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/api/collab/pairs", json={"partner_id": "emp_missing"}, headers=admin
            ).status_code
            == 404
        )
        assert client.post("/api/collab/pairs", json={}, headers=admin).status_code == 422

        listed = client.get("/api/collab/pairs", headers=colleague)
        assert listed.status_code == 200, listed.text
        assert [item["pair_id"] for item in listed.json()] == [pair_id]

        captured: list[tuple[str, dict]] = []

        class _SpyBus:
            def publish(self, kind: str, payload: dict) -> None:
                captured.append((kind, payload))

        client.app.state.container.collab_messages._events = _SpyBus()

        sent = client.post(
            "/api/collab/messages",
            json={
                "pair_id": pair_id,
                "body": "同步一下",
                "recipient_id": partner_id,
            },
            headers=admin,
        )
        assert sent.status_code == 201, sent.text
        assert sent.json()["pair_id"] == pair_id
        assert sent.json()["sender_id"] == me
        assert sent.json()["recipient_id"] == partner_id

        # 公开大屏事件：message.created 只带脱敏字段，可用于实时气泡
        created_events = [
            payload for kind, payload in captured if kind == "message.created"
        ]
        assert len(created_events) == 1
        event = created_events[0]
        assert set(event) == {
            "message_id",
            "pair_id",
            "kind",
            "body",
            "created_at",
        }
        assert event["message_id"] == sent.json()["message_id"]
        assert event["pair_id"] == pair_id
        assert event["body"] == "同步一下"
        assert "sender_id" not in event
        assert "recipient_id" not in event

        messages = client.get(
            "/api/collab/messages", params={"pair_id": pair_id}, headers=colleague
        )
        assert [item["body"] for item in messages.json()] == ["同步一下"]

        public_messages = client.get(
            "/api/public/collab/messages", params={"pair_id": pair_id}
        )
        assert public_messages.status_code == 200, public_messages.text
        assert len(public_messages.json()) == 1
        public_message = public_messages.json()[0]
        assert set(public_message) == {
            "message_id",
            "kind",
            "body",
            "created_at",
            "delivery_status",
            "pair_id",
        }
        assert public_message["message_id"] == sent.json()["message_id"]
        assert public_message["body"] == "同步一下"
        assert public_message["pair_id"] == pair_id
        assert client.get("/api/public/collab/messages").status_code == 422

        assert client.get("/api/tasks", headers=admin).json()["items"] == []

        created_task = client.post(
            "/api/tasks",
            json={"title": "公开任务", "owner_id": partner_id},
            headers=admin,
        )
        assert created_task.status_code == 201, created_task.text
        task_id = created_task.json()["task_id"]
        public_task_row = client.get(f"/api/public/collab/tasks/{task_id}")
        assert public_task_row.status_code == 200, public_task_row.text
        row = public_task_row.json()
        # 公开任务投影不得暴露 created_by / owner_id / 流程标识 / 内部节点 ID
        assert set(row) == {
            "task_id",
            "title",
            "state",
            "created_at",
            "updated_at",
            "nodes",
        }
        assert row["task_id"] == task_id
        assert row["title"] == "公开任务"
        for node in row["nodes"]:
            assert set(node) == {"name", "order", "state"}

        ended = client.post(f"/api/collab/pairs/{pair_id}/end", headers=colleague)
        assert ended.status_code == 204

        closed = client.get(
            "/api/collab/pairs", params={"state": "ended"}, headers=admin
        ).json()
        assert closed[0]["pair_id"] == pair_id
        assert closed[0]["ended_at"] is not None

        rejected = client.post(
            "/api/collab/messages",
            json={"pair_id": pair_id, "body": "还能发吗"},
            headers=admin,
        )
        assert rejected.status_code == 409

        assert (
            client.post(
                "/api/collab/pairs/pair_missing/end", headers=admin
            ).status_code
            == 404
        )


def test_public_messages_require_active_pair(tmp_path):
    """L6：公开消息只对进行中的结对开放，未知或已结束一律返回空数组。"""
    with _client(tmp_path) as client:
        admin = _headers(_bootstrap(client))
        partner_id, _ = _hire(client, admin, "搭档")
        pair_id = client.post(
            "/api/collab/pairs", json={"partner_id": partner_id}, headers=admin
        ).json()["pair_id"]
        client.post(
            "/api/collab/messages",
            json={"pair_id": pair_id, "body": "进行中的消息"},
            headers=admin,
        )
        active = client.get(
            "/api/public/collab/messages", params={"pair_id": pair_id}
        )
        assert active.status_code == 200, active.text
        assert [item["body"] for item in active.json()] == ["进行中的消息"]

        client.post(f"/api/collab/pairs/{pair_id}/end", headers=admin)
        closed = client.get(
            "/api/public/collab/messages", params={"pair_id": pair_id}
        )
        assert closed.status_code == 200, closed.text
        assert closed.json() == []

        unknown = client.get(
            "/api/public/collab/messages", params={"pair_id": "pair_missing"}
        )
        assert unknown.status_code == 200, unknown.text
        assert unknown.json() == []


def test_public_layout_carries_active_pair(tmp_path):
    with _client(tmp_path) as client:
        admin = _headers(_bootstrap(client))
        me = client.get("/api/identity/me", headers=admin).json()["employee_id"]
        partner_id, _ = _hire(client, admin, "搭档")
        pair = client.post(
            "/api/collab/pairs", json={"partner_id": partner_id}, headers=admin
        ).json()

        seats = [
            seat
            for floor in client.get("/api/public/layout").json()["floors"]
            for room in floor["rooms"]
            for seat in room["seats"]
        ]
        free = [seat["seat_id"] for seat in seats if seat["agent"] is None]
        assert len(free) >= 2
        for employee_id, seat_id in ((me, free[0]), (partner_id, free[1])):
            seated = client.put(
                f"/api/seats/{seat_id}/assign",
                json={"employee_id": employee_id},
                headers=admin,
            )
            assert seated.status_code == 200, seated.text

        agents = [
            seat["agent"]
            for floor in client.get("/api/public/layout").json()["floors"]
            for room in floor["rooms"]
            for seat in room["seats"]
            if seat["agent"] is not None
        ]
        assert len(agents) == 2
        # 公开布局直接带结对信息，大屏无需管理员名册即可连线
        assert {agent["pair_id"] for agent in agents} == {pair["pair_id"]}
        partners = {agent["display_name"]: agent["partner_name"] for agent in agents}
        assert partners["超级管理员"] == "搭档"
        assert partners["搭档"] == "超级管理员"


def test_pair_and_messages_reject_outsiders(tmp_path):
    with _client(tmp_path) as client:
        admin = _headers(_bootstrap(client))
        partner_id, partner_token = _hire(client, admin, "搭档")
        outsider_id, outsider_token = _hire(client, admin, "旁观者")
        assert outsider_id != partner_id

        pair_id = client.post(
            "/api/collab/pairs", json={"partner_id": partner_id}, headers=admin
        ).json()["pair_id"]
        client.post(
            "/api/collab/messages",
            json={"pair_id": pair_id, "body": "内部消息"},
            headers=admin,
        )

        outsider = _headers(outsider_token)
        assert (
            client.get(
                "/api/collab/messages", params={"pair_id": pair_id}, headers=outsider
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/collab/messages",
                json={"pair_id": pair_id, "body": "插话"},
                headers=outsider,
            ).status_code
            == 403
        )
        assert (
            client.post(f"/api/collab/pairs/{pair_id}/end", headers=outsider).status_code
            == 403
        )
        assert client.get("/api/collab/pairs", headers=outsider).json() == []


def test_public_collab_tasks_hide_creator(tmp_path):
    with _client(tmp_path) as client:
        admin = _headers(_bootstrap(client))
        owner_id = client.get("/api/identity/me", headers=admin).json()["employee_id"]
        created = client.post(
            "/api/tasks",
            json={"title": "公开任务", "owner_id": owner_id},
            headers=admin,
        )
        assert created.status_code == 201, created.text
        assert created.json()["created_by"] == owner_id

        response = client.get(f"/api/public/collab/tasks/{created.json()['task_id']}")
        assert response.status_code == 200, response.text
        public_task = response.json()
        assert set(public_task) == {
            "task_id",
            "title",
            "state",
            "created_at",
            "updated_at",
            "nodes",
        }
        assert public_task["task_id"] == created.json()["task_id"]
        assert "created_by" not in public_task
        assert "owner_id" not in public_task
        assert "workflow_id" not in public_task
        for node in public_task["nodes"]:
            assert set(node) == {"name", "order", "state"}


def test_public_seat_tasks_resolve_occupant(tmp_path):
    """Twin 抽屉按工位取任务：服务端解析员工，不暴露员工标识。"""
    with _client(tmp_path) as client:
        admin = _headers(_bootstrap(client))
        employee_id, _ = _hire(client, admin, "工位任务员工")
        seats = [
            seat
            for floor in client.get("/api/public/layout").json()["floors"]
            for room in floor["rooms"]
            for seat in room["seats"]
        ]
        occupied_seat = seats[0]["seat_id"]
        empty_seat = seats[1]["seat_id"]
        seated = client.put(
            f"/api/seats/{occupied_seat}/assign",
            json={"employee_id": employee_id},
            headers=admin,
        )
        assert seated.status_code == 200, seated.text
        created = client.post(
            "/api/tasks",
            json={"title": "工位任务", "owner_id": employee_id},
            headers=admin,
        )
        assert created.status_code == 201, created.text

        rows = client.get(f"/api/public/collab/seats/{occupied_seat}/tasks")
        assert rows.status_code == 200, rows.text
        assert [row["task_id"] for row in rows.json()] == [created.json()["task_id"]]
        assert set(rows.json()[0]) == {
            "task_id",
            "title",
            "state",
            "created_at",
            "updated_at",
            "nodes",
        }

        empty = client.get(f"/api/public/collab/seats/{empty_seat}/tasks")
        assert empty.status_code == 200, empty.text
        assert empty.json() == []
        assert client.get("/api/public/collab/seats/seat_missing/tasks").status_code == 404
