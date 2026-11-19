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
    applied = client.post(
        "/api/identity/staff", json={"display_name": name, "account_type": "human"}
    )
    assert applied.status_code == 201, applied.text
    employee_id = applied.json()["employee"]["employee_id"]
    client.post(
        f"/api/identity/staff/{employee_id}/review",
        json={"approved": True},
        headers=admin,
    )
    activated = client.post(
        f"/api/identity/staff/{employee_id}/activate", headers=admin
    )
    assert activated.status_code == 200, activated.text
    return employee_id, activated.json()["token"]


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

        sent = client.post(
            "/api/collab/messages",
            json={"pair_id": pair_id, "body": "同步一下"},
            headers=admin,
        )
        assert sent.status_code == 201, sent.text
        assert sent.json()["pair_id"] == pair_id

        messages = client.get(
            "/api/collab/messages", params={"pair_id": pair_id}, headers=colleague
        )
        assert [item["body"] for item in messages.json()] == ["同步一下"]

        public_messages = client.get(
            "/api/public/collab/messages", params={"pair_id": pair_id}
        )
        assert public_messages.status_code == 200, public_messages.text
        assert len(public_messages.json()) == 1
        assert (
            client.get("/api/public/collab/messages").status_code == 422
        )

        assert client.get("/api/collab/tasks", headers=admin).json() == []
        public_tasks = client.get(
            "/api/public/collab/tasks", params={"owner_id": me}
        )
        assert public_tasks.status_code == 200, public_tasks.text
        assert public_tasks.json() == []
        assert client.get("/api/public/collab/tasks").status_code == 422

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
