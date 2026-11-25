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
    position = client.post(
        "/api/positions", json={"name": "研究岗"}, headers=headers
    )
    assert position.status_code == 201, position.text
    invite = client.post(
        "/api/agent-invites",
        json={"employee_name": "执行者", "position_id": position.json()["position_id"]},
        headers=headers,
    )
    assert invite.status_code == 201, invite.text
    agent = client.post(
        "/api/agents/register",
        json={
            "invite_code": invite.json()["invite_code"],
            "name": "研究员",
            "framework": "claude",
        },
    )
    assert agent.status_code == 201, agent.text
    body = agent.json()
    seat_id = [
        seat["seat_id"]
        for floor in client.get("/api/layout", headers=headers).json()["floors"]
        for room in floor["rooms"]
        for seat in room["seats"]
    ][0]
    seated = client.put(
        f"/api/seats/{seat_id}/assign",
        json={"employee_id": body["employee_id"]},
        headers=headers,
    )
    assert seated.status_code == 200, seated.text
    return body["agent_id"], body["employee_id"]


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

        # 取消是新的终态路径（失败只保留给历史任务）；概览只统计当日失败数
        cancelled = client.post(
            "/api/tasks", json={"title": "失败示例"}, headers=headers
        ).json()
        cancelled_resp = client.post(
            f"/api/tasks/{cancelled['task_id']}/cancel",
            json={"reason": "manual"},
            headers=headers,
        )
        assert cancelled_resp.status_code == 200, cancelled_resp.text

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
        assert body["tasks_failed_today"] == 0

        points = {item["metric"]: item["value"] for item in body["metrics"]}
        assert points["tasks.active"] == 1
        assert points["tasks.failed_today"] == 0
        assert points["agents.online"] == 1
        assert points["agents.total"] == 1
        assert points["workflows.total"] == 1
