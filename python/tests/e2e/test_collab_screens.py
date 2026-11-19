"""大屏同步端到端：公开登记、心跳、离线与管理端列表/聚焦。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from mailbus.bootstrap.main import create_app
from mailbus.bootstrap.settings import Settings


def _client(tmp_path) -> TestClient:
    return TestClient(create_app(Settings(data_dir=tmp_path)))


def _bootstrap(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/identity/bootstrap/super-admin", json={"display_name": "超级管理员"}
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_public_screen_register_heartbeat_leave(tmp_path):
    with _client(tmp_path) as client:
        headers = _bootstrap(client)

        created = client.post(
            "/api/public/collab/screens",
            json={"screen_id": "screen-ab12", "name": "大屏 ab12"},
        )
        assert created.status_code == 201, created.text
        assert created.json()["online"] is True

        beat = client.post(
            "/api/public/collab/screens/screen-ab12/heartbeat",
            json={"floor_id": "f2", "seat_id": None},
        )
        assert beat.status_code == 200, beat.text
        assert beat.json() == {"ok": True}

        listed = client.get("/api/collab/screens", headers=headers)
        assert listed.status_code == 200, listed.text
        assert listed.json()[0]["screen_id"] == "screen-ab12"
        assert listed.json()[0]["floor_id"] == "f2"

        focus = client.post(
            "/api/collab/screens/screen-ab12/focus",
            json={"floor_id": "f2", "seat_id": None},
            headers=headers,
        )
        assert focus.status_code == 204, focus.text

        left = client.post("/api/public/collab/screens/screen-ab12/leave")
        assert left.status_code == 204, left.text
        offline = client.get("/api/collab/screens", headers=headers).json()[0]
        assert offline["online"] is False


def test_admin_screen_register_and_validation(tmp_path):
    with _client(tmp_path) as client:
        headers = _bootstrap(client)

        created = client.post(
            "/api/collab/screens",
            json={"name": "管理端大屏", "floor_id": "f1"},
            headers=headers,
        )
        assert created.status_code == 201, created.text
        assert created.json()["screen_id"].startswith("screen_")

        bad = client.post(
            "/api/collab/screens/screen-unknown/focus",
            json={"seat_id": None},
            headers=headers,
        )
        assert bad.status_code == 422

        missing = client.post(
            "/api/public/collab/screens/screen-unknown/heartbeat", json={}
        )
        assert missing.status_code == 404
