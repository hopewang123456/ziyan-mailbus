"""B6 集成：file_bus 入站与 HTTP 入口共用同一鉴权。"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from mailbus.bootstrap.main import create_app
from mailbus.bootstrap.settings import Settings


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bootstrap(client: TestClient) -> str:
    response = client.post(
        "/api/identity/bootstrap/super-admin", json={"display_name": "超级管理员"}
    )
    assert response.status_code == 201, response.text
    return response.json()["token"]


def _staff(client: TestClient, admin_headers: dict[str, str]) -> tuple[str, str]:
    applied = client.post(
        "/api/identity/staff", json={"display_name": "员工丁", "account_type": "human"}
    )
    employee_id = applied.json()["employee"]["employee_id"]
    client.post(
        f"/api/identity/staff/{employee_id}/review",
        json={"approved": True},
        headers=admin_headers,
    )
    activated = client.post(
        f"/api/identity/staff/{employee_id}/activate", headers=admin_headers
    )
    return employee_id, activated.json()["token"]


def test_file_bus_ingest_accepts_and_rejects_like_http(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        admin_token = _bootstrap(client)
        admin_headers = _headers(admin_token)
        employee_id, staff_token = _staff(client, admin_headers)
        ingress = app.state.container.file_bus_ingress
        inbound = tmp_path / "file_bus" / "inbound"
        inbound.mkdir(parents=True, exist_ok=True)

        (inbound / "ok.json").write_text(
            json.dumps(
                {
                    "token": admin_token,
                    "body": "来自文件总线",
                    "recipient_id": employee_id,
                }
            ),
            encoding="utf-8",
        )
        assert ingress.poll_once() == (1, 0)
        inbox = client.get("/api/inbox", headers=_headers(staff_token)).json()
        assert [item["body"] for item in inbox] == ["来自文件总线"]

        (inbound / "denied.json").write_text(
            json.dumps({"token": staff_token, "body": "越权文件"}), encoding="utf-8"
        )
        assert ingress.poll_once() == (0, 1)
        assert (tmp_path / "file_bus" / "rejected").exists()
        assert (tmp_path / "file_bus" / "processed" / "ok.json").exists()
        assert len(client.get("/api/inbox", headers=_headers(staff_token)).json()) == 1
