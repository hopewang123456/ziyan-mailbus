"""B3 端到端：Agent 台账、员工绑定与布局执行态投影。"""

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


def _create_agent(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(
        "/api/agents",
        json={
            "name": "研究员",
            "framework": "claude",
            "model": "deepseek-v4",
            "endpoint": "http://127.0.0.1:9001",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _seat(client: TestClient, headers: dict[str, str]) -> str:
    seats = client.get("/api/org/seats", headers=headers).json()
    return seats[0]["seat_id"]


def _active_staff(
    client: TestClient, headers: dict[str, str], seat_id: str, agent_id: str
) -> str:
    applied = client.post(
        "/api/identity/staff",
        json={
            "display_name": "执行者",
            "account_type": "human",
            "seat_id": seat_id,
            "agent_id": agent_id,
        },
    )
    assert applied.status_code == 201, applied.text
    employee_id = applied.json()["employee"]["employee_id"]
    client.post(
        f"/api/identity/staff/{employee_id}/review",
        json={"approved": True},
        headers=headers,
    )
    client.post(f"/api/identity/staff/{employee_id}/activate", headers=headers)
    return employee_id


def _running_task(
    client: TestClient, headers: dict[str, str], owner_id: str
) -> dict:
    workflow = client.post(
        "/api/workflows", json={"name": "研究工作流"}, headers=headers
    )
    assert workflow.status_code == 201, workflow.text
    workflow_id = workflow.json()["workflow_id"]
    version = client.post(
        f"/api/workflows/{workflow_id}/versions",
        json={"nodes": [{"name": "收集"}, {"name": "执行"}]},
        headers=headers,
    )
    assert version.status_code == 201, version.text
    client.post(
        f"/api/workflows/{workflow_id}/versions/1/publish", headers=headers
    )
    task = client.post(
        "/api/tasks",
        json={
            "title": "季度研究",
            "owner_id": owner_id,
            "workflow_id": workflow_id,
            "workflow_version": 1,
        },
        headers=headers,
    )
    assert task.status_code == 201, task.text
    task_id = task.json()["task_id"]
    client.post(f"/api/tasks/{task_id}/dispatch", headers=headers)
    advanced = client.post(
        f"/api/tasks/{task_id}/advance", json={"outcome": "running"}, headers=headers
    )
    assert advanced.status_code == 200, advanced.text
    return advanced.json()


def _seat_agent(
    client: TestClient,
    seat_id: str,
    headers: dict[str, str],
    public: bool = False,
) -> dict:
    path = "/api/public/layout" if public else "/api/layout"
    layout = client.get(path, headers=None if public else headers)
    assert layout.status_code == 200, layout.text
    seats = [
        seat
        for floor in layout.json()["floors"]
        for room in floor["rooms"]
        for seat in room["seats"]
    ]
    agent = next(item for item in seats if item["seat_id"] == seat_id)["agent"]
    assert agent is not None
    return agent


def test_agent_ledger_crud_and_permission(tmp_path):
    with _client(tmp_path) as client:
        admin_headers = _headers(_bootstrap(client))
        agent = _create_agent(client, admin_headers)
        assert agent["agent_id"].startswith("agent_")
        assert agent["enabled"] is True

        listed = client.get("/api/agents", headers=admin_headers)
        assert listed.status_code == 200, listed.text
        assert [item["agent_id"] for item in listed.json()] == [agent["agent_id"]]

        updated = client.patch(
            f"/api/agents/{agent['agent_id']}",
            json={"name": "高级研究员", "enabled": False},
            headers=admin_headers,
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["name"] == "高级研究员"
        assert updated.json()["enabled"] is False
        assert updated.json()["framework"] == "claude"

        staff = client.post(
            "/api/identity/staff", json={"display_name": "小王", "account_type": "human"}
        ).json()["employee"]["employee_id"]
        client.post(
            f"/api/identity/staff/{staff}/review",
            json={"approved": True},
            headers=admin_headers,
        )
        token = client.post(
            f"/api/identity/staff/{staff}/activate", headers=admin_headers
        ).json()["token"]
        denied = client.post(
            "/api/agents", json={"name": "越权 Agent"}, headers=_headers(token)
        )
        assert denied.status_code == 403


def test_employee_binding_and_layout_execution(tmp_path):
    with _client(tmp_path) as client:
        admin_headers = _headers(_bootstrap(client))
        agent = _create_agent(client, admin_headers)
        seat_id = _seat(client, admin_headers)
        employee_id = _active_staff(
            client, admin_headers, seat_id, agent["agent_id"]
        )

        staff = client.get(
            "/api/identity/staff?status=all", headers=admin_headers
        ).json()
        view = next(item for item in staff if item["employee_id"] == employee_id)
        assert view["agent_id"] == agent["agent_id"]
        assert view["agent_name"] == "研究员"
        assert view["agent_framework"] == "claude"

        idle = _seat_agent(client, seat_id, admin_headers)
        assert idle["bound_agent_id"] == agent["agent_id"]
        assert idle["agent_name"] == "研究员"
        assert idle["agent_framework"] == "claude"
        assert idle["task_state"] == ""

        _running_task(client, admin_headers, employee_id)
        busy = _seat_agent(client, seat_id, admin_headers)
        assert busy["status"] == "busy"
        assert busy["task"] == "季度研究"
        assert busy["task_state"] == "running"
        assert busy["current_node"] == "收集"
        assert busy["node_state"] == "running"
        assert busy["progress_done"] == 0
        assert busy["progress_total"] == 2

        public = _seat_agent(client, seat_id, admin_headers, public=True)
        assert "agent_id" not in public
        assert "bound_agent_id" not in public
        assert "task_id" not in public
        assert "last_heartbeat" not in public
        assert public["agent_name"] == "研究员"
        assert public["agent_framework"] == "claude"
        assert public["task_state"] == "running"
        assert public["progress_total"] == 2

        unbound = client.patch(
            f"/api/identity/staff/{employee_id}/agent",
            json={"agent_id": None},
            headers=admin_headers,
        )
        assert unbound.status_code == 200, unbound.text
        assert unbound.json()["agent_id"] is None
        assert _seat_agent(client, seat_id, admin_headers)["bound_agent_id"] == ""

        missing = client.post(
            "/api/identity/staff",
            json={
                "display_name": "绑定失败",
                "account_type": "human",
                "agent_id": "agent_missing",
            },
        )
        assert missing.status_code == 404
