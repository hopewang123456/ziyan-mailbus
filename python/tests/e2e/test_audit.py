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
        assert empty.json()["items"] == []

        client.patch(
            "/api/metrics/rules/agents_offline",
            json={"fields": {"enabled": True}},
            headers=headers,
        )
        # 旧指标规则视图仍驱动 alerts.active；/api/alerts 只承载 ops_alerts
        point = client.get(
            "/api/metrics/query", params={"metric": "alerts.active"}, headers=headers
        ).json()["points"][0]
        assert point["value"] == 1
        assert client.get("/api/alerts", headers=headers).json()["items"] == []


def test_audit_stats_are_scoped_to_data_scope(tmp_path):
    """M11：非全局账号的统计不含他队任务与审核人。"""
    with _client(tmp_path) as client:
        admin = _headers(_bootstrap(client))
        created = client.post(
            "/api/tasks", json={"title": "管理员任务"}, headers=admin
        )
        task_id = created.json()["task_id"]
        approval = client.post(
            "/api/approvals",
            json={"task_id": task_id, "title": "审核", "tier": "advisory"},
            headers=admin,
        ).json()
        client.post(
            f"/api/approvals/{approval['approval_id']}/resolve",
            json={"decision": "approved"},
            headers=admin,
        )

        admin_stats = client.get("/api/tasks/audit/stats", headers=admin).json()
        assert admin_stats["total_tasks"] == 1
        assert admin_stats["by_reviewer"]

        invite = client.post(
            "/api/employees/invite",
            json={"display_name": "路人", "permissions": []},
            headers=admin,
        ).json()
        other = client.post(
            "/api/invites/accept",
            json={"invite_code": invite["invite_code"], "display_name": "路人"},
        ).json()
        other_stats = client.get(
            "/api/tasks/audit/stats", headers=_headers(other["token"])
        ).json()
        assert other_stats["total_tasks"] == 0
        assert other_stats["by_reviewer"] == {}
