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
    assert body["schema_version"] == 14
    assert (tmp_path / "mailbus.db").exists()


def test_openapi_is_served(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))

    with TestClient(app) as client:
        response = client.get("/api/openapi.json")

    assert response.status_code == 200
    assert "/api/health" in response.json()["paths"]


def test_oversized_request_body_is_rejected(tmp_path):
    """L5：请求体超过上限时直接 413，不进入业务解析。"""
    app = create_app(Settings(data_dir=tmp_path, max_body_bytes=64))

    with TestClient(app) as client:
        response = client.post(
            "/api/identity/bootstrap/super-admin",
            json={"display_name": "超" * 100},
        )
        ok = client.get("/api/health")

    assert response.status_code == 413
    assert response.json()["error_code"] == "payload_too_large"
    assert ok.status_code == 200
