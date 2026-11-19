"""B5 端到端：收件箱为投影、消息发送与运营观测。"""

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


def _staff(client: TestClient, admin_headers: dict[str, str], name: str) -> tuple[str, str]:
    applied = client.post(
        "/api/identity/staff", json={"display_name": name, "account_type": "human"}
    )
    assert applied.status_code == 201, applied.text
    employee_id = applied.json()["employee"]["employee_id"]
    client.post(
        f"/api/identity/staff/{employee_id}/review",
        json={"approved": True},
        headers=admin_headers,
    )
    activated = client.post(
        f"/api/identity/staff/{employee_id}/activate", headers=admin_headers
    )
    assert activated.status_code == 200, activated.text
    return employee_id, activated.json()["token"]


def test_inbox_is_projection_and_overview_log_reflect_messages(tmp_path):
    with _client(tmp_path) as client:
        admin_token = _bootstrap(client)
        admin_headers = _headers(admin_token)
        employee_a, token_a = _staff(client, admin_headers, "员工甲")
        employee_b, token_b = _staff(client, admin_headers, "员工乙")

        direct = client.post(
            "/api/messages",
            json={"body": "只发给乙", "recipient_id": employee_b},
            headers=admin_headers,
        )
        assert direct.status_code == 201, direct.text
        direct_id = direct.json()["message_id"]

        inbox_b = client.get("/api/inbox", headers=_headers(token_b)).json()
        assert [item["message_id"] for item in inbox_b] == [direct_id]
        assert client.get("/api/inbox", headers=_headers(token_a)).json() == []
        assert client.get(f"/api/messages/{direct_id}", headers=admin_headers).status_code == 200

        broadcast = client.post(
            "/api/messages", json={"body": "全员通知"}, headers=admin_headers
        )
        assert broadcast.status_code == 201, broadcast.text

        assert len(client.get("/api/inbox", headers=_headers(token_a)).json()) == 1
        assert len(client.get("/api/inbox", headers=_headers(token_b)).json()) == 2

        # 收件箱没有独立写入路径
        assert client.post("/api/inbox", json={}, headers=admin_headers).status_code == 405

        overview = client.get("/api/overview", headers=admin_headers)
        assert overview.status_code == 200, overview.text
        body = overview.json()
        assert body["employees_total"] == 3
        assert body["employees_active"] == 3
        assert body["messages_total"] == 2

        log = client.get("/api/log?limit=20", headers=admin_headers)
        assert log.status_code == 200, log.text
        assert any(entry["kind"] == "message.sent" for entry in log.json())

        # 重复激活/无关路径保持 404，避免把观测路由误写成写入口
        assert client.get("/api/messages/missing", headers=admin_headers).status_code == 404


def test_message_search_scope_and_filters(tmp_path):
    with _client(tmp_path) as client:
        admin_headers = _headers(_bootstrap(client))
        employee_a, token_a = _staff(client, admin_headers, "员工甲")
        employee_b, token_b = _staff(client, admin_headers, "员工乙")

        direct_id = client.post(
            "/api/messages",
            json={"body": "只发给乙", "recipient_id": employee_b},
            headers=admin_headers,
        ).json()["message_id"]
        client.post("/api/messages", json={"body": "全员通知"}, headers=admin_headers)

        # 超管看全部
        everything = client.get("/api/messages", headers=admin_headers)
        assert everything.status_code == 200, everything.text
        assert len(everything.json()) == 2
        assert all("delivery_status" in item for item in everything.json())

        # 普通用户只看自己收发（含广播）
        seen_a = [item["message_id"] for item in client.get(
            "/api/messages", headers=_headers(token_a)
        ).json()]
        assert direct_id not in seen_a
        assert len(seen_a) == 1

        seen_b = [item["message_id"] for item in client.get(
            "/api/messages", headers=_headers(token_b)
        ).json()]
        assert direct_id in seen_b

        # 明细同样受范围约束
        assert (
            client.get(f"/api/messages/{direct_id}", headers=_headers(token_a)).status_code
            == 403
        )
        assert (
            client.get(f"/api/messages/{direct_id}/attempts", headers=_headers(token_a)).status_code
            == 403
        )

        # 过滤参数：按参与人 / 非法状态
        by_agent = client.get(
            f"/api/messages?agent={employee_b}", headers=admin_headers
        ).json()
        assert [item["message_id"] for item in by_agent] == [direct_id]
        assert (
            client.get("/api/messages?status=bogus", headers=admin_headers).status_code
            == 422
        )
