"""概览聚合端到端：员工、Agent、任务、流程与指标快照。"""

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


def _active_agent_employee(
    client: TestClient, headers: dict[str, str]
) -> tuple[str, str]:
    agent = client.post(
        "/api/agents",
        json={"name": "研究员", "framework": "claude"},
        headers=headers,
    )
    assert agent.status_code == 201, agent.text
    seat_id = client.get("/api/org/seats", headers=headers).json()[0]["seat_id"]
    applied = client.post(
        "/api/identity/staff",
        json={
            "display_name": "执行者",
            "account_type": "human",
            "seat_id": seat_id,
            "agent_id": agent.json()["agent_id"],
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
    return agent.json()["agent_id"], employee_id


def _workflow(client: TestClient, headers: dict[str, str]) -> str:
    created = client.post(
        "/api/workflows", json={"name": "内容生产"}, headers=headers
    )
    workflow_id = created.json()["workflow_id"]
    client.post(
        f"/api/workflows/{workflow_id}/versions",
        json={"nodes": [{"name": "调研"}, {"name": "撰写"}]},
        headers=headers,
    )
    client.post(
        f"/api/workflows/{workflow_id}/versions/1/publish", headers=headers
    )
    return workflow_id


def test_overview_aggregates_domains_and_metrics(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))
        _, employee_id = _active_agent_employee(client, headers)
        workflow_id = _workflow(client, headers)

        task = client.post(
            "/api/tasks",
            json={
                "title": "季度报告",
                "workflow_id": workflow_id,
                "owner_id": employee_id,
            },
            headers=headers,
        )
        assert task.status_code == 201, task.text
        task_id = task.json()["task_id"]
        client.post(f"/api/tasks/{task_id}/dispatch", headers=headers)

        failed = client.post(
            "/api/tasks", json={"title": "失败示例"}, headers=headers
        ).json()
        client.post(f"/api/tasks/{failed['task_id']}/dispatch", headers=headers)
        client.post(
            f"/api/tasks/{failed['task_id']}/advance",
            json={"outcome": "failed"},
            headers=headers,
        )

        overview = client.get("/api/overview", headers=headers)
        assert overview.status_code == 200, overview.text
        body = overview.json()
        assert body["agents_total"] == 1
        assert body["agents_enabled"] == 1
        assert body["agents_online"] == 1
        assert body["agents_busy"] == 1
        assert body["seats_occupied"] == 1
        assert body["workflows_total"] == 1
        assert body["workflows_published"] == 1
        assert body["tasks_total"] == 2
        assert body["tasks_active"] == 1
        assert body["tasks_failed_today"] == 1

        points = {item["metric"]: item["value"] for item in body["metrics"]}
        assert points["tasks.active"] == 1
        assert points["tasks.failed_today"] == 1
        assert points["agents.online"] == 1
        assert points["agents.total"] == 1
        assert points["workflows.total"] == 1
