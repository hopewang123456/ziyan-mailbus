"""B0 端到端：应用可启动、健康探测可用、迁移已应用。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from mailbus.bootstrap.main import create_app
from mailbus.bootstrap.settings import Settings


def test_health_reports_ok_and_schema_version(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "mailbus"
    assert body["schema_version"] == 12
    assert (tmp_path / "mailbus.db").exists()


def test_openapi_is_served(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))

    with TestClient(app) as client:
        response = client.get("/api/openapi.json")

    assert response.status_code == 200
    assert "/api/health" in response.json()["paths"]
