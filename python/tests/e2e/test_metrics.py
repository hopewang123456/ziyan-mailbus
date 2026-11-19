"""指标治理端到端：manifest、查询、规则、布局与告警联动。"""

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


def test_metrics_manifest_query_rules_and_layout(tmp_path):
    with _client(tmp_path) as client:
        headers = _headers(_bootstrap(client))

        manifest = client.get("/api/metrics/manifest", headers=headers)
        assert manifest.status_code == 200, manifest.text
        assert manifest.json()["manifest"]["metrics"]

        query = client.get("/api/metrics/query", headers=headers)
        assert query.status_code == 200, query.text
        points = {item["metric"]: item for item in query.json()["points"]}
        assert points["tasks.active"]["value"] == 0
        assert points["alerts.active"]["value"] == 0

        rules = client.get("/api/metrics/rules", headers=headers).json()["rules"]
        ids = {item["id"] for item in rules}
        assert {"tasks_failed_today", "agents_offline"} <= ids

        patched = client.patch(
            "/api/metrics/rules/tasks_failed_today",
            json={"fields": {"threshold": 2, "enabled": True}},
            headers=headers,
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["threshold"] == 2

        layout = client.get("/api/metrics/layout", headers=headers)
        assert layout.json()["layout"]["hidden"] == []
        hidden = client.patch(
            "/api/metrics/layout",
            json={"hidden": ["tasks.active"]},
            headers=headers,
        )
        assert hidden.status_code == 200, hidden.text
        assert hidden.json()["layout"]["hidden"] == ["tasks.active"]
        assert (
            client.get("/api/metrics/layout", headers=headers).json()["layout"][
                "hidden"
            ]
            == ["tasks.active"]
        )

        # 启用「无在线 Agent」规则后应产生告警，并反映到 alerts.active
        client.patch(
            "/api/metrics/rules/agents_offline",
            json={"fields": {"enabled": True}},
            headers=headers,
        )
        alerts = client.get("/api/alerts", headers=headers)
        assert alerts.status_code == 200, alerts.text
        assert [item["id"] for item in alerts.json()["alerts"]] == ["agents_offline"]
        point = client.get(
            "/api/metrics/query",
            params={"metric": "alerts.active"},
            headers=headers,
        ).json()["points"][0]
        assert point["value"] == 1
        assert point["error"] is None


def test_metrics_writes_require_system_config(tmp_path):
    with _client(tmp_path) as client:
        admin_headers = _headers(_bootstrap(client))
        applied = client.post(
            "/api/identity/staff", json={"display_name": "小王", "account_type": "human"}
        )
        employee_id = applied.json()["employee"]["employee_id"]
        client.post(
            f"/api/identity/staff/{employee_id}/review",
            json={"approved": True},
            headers=admin_headers,
        )
        token = client.post(
            f"/api/identity/staff/{employee_id}/activate", headers=admin_headers
        ).json()["token"]
        denied = client.patch(
            "/api/metrics/rules/tasks_failed_today",
            json={"fields": {"enabled": True}},
            headers=_headers(token),
        )
        assert denied.status_code == 403
