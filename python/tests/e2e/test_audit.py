"""审计与告警端到端：审核统计与规则告警。"""

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


def test_audit_stats_and_alerts(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))
        created = client.post(
            "/api/tasks", json={"title": "待审任务"}, headers=headers
        )
        assert created.status_code == 201, created.text

        stats = client.get("/api/tasks/audit/stats", headers=headers)
        assert stats.status_code == 200, stats.text
        body = stats.json()
        assert body["total_tasks"] == 1
        assert body["audited_tasks"] == 0
        assert body["pending_audit_tasks"] == 0
        assert body["pass_count"] == 0
        assert body["fail_count"] == 0
        assert body["by_reviewer"] == {}

        empty = client.get("/api/alerts", headers=headers)
        assert empty.status_code == 200, empty.text
        assert empty.json()["alerts"] == []

        client.patch(
            "/api/metrics/rules/agents_offline",
            json={"fields": {"enabled": True}},
            headers=headers,
        )
        alerts = client.get("/api/alerts", headers=headers).json()["alerts"]
        assert len(alerts) == 1
        assert alerts[0]["type"] == "agents.online"
        assert alerts[0]["severity"] == "warn"
