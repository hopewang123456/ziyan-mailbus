"""大屏同步端到端：登记密钥、心跳/离线、草稿/发布、公开配置与布局。"""

from __future__ import annotations

import sqlite3
from contextlib import closing

from fastapi.testclient import TestClient

from mailbus.bootstrap.main import create_app
from mailbus.bootstrap.settings import Settings


def _client(tmp_path) -> TestClient:
    return TestClient(create_app(Settings(data_dir=tmp_path)))


def _headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/identity/bootstrap/super-admin", json={"display_name": "超级管理员"}
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _register(client: TestClient, **payload) -> dict:
    response = client.post("/api/public/collab/screens", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_register_returns_secret_once_and_never_stores_plaintext(tmp_path):
    with _client(tmp_path) as client:
        admin = _headers(client)
        created = _register(client, name="大屏 A")
        screen_id = created["screen_id"]
        secret = created["screen_secret"]
        assert screen_id.startswith("screen_")
        assert secret
        assert created["config_version"] == 1

        # 持有 id + secret 才复用；不回显第二次
        reused = _register(client, screen_id=screen_id, secret=secret)
        assert reused["screen_id"] == screen_id
        assert reused["screen_secret"] is None

        # 缺 secret / secret 错误：一律新屏，绝不覆盖既有配置
        fresh = _register(client, screen_id=screen_id, name="新屏")
        assert fresh["screen_id"] != screen_id
        wrong = _register(client, screen_id=screen_id, secret="wrong-key")
        assert wrong["screen_id"] != screen_id

        with closing(sqlite3.connect(tmp_path / "mailbus.db")) as conn:
            stored = conn.execute(
                "SELECT secret_hash, source FROM collab_screens WHERE screen_id = ?",
                (screen_id,),
            ).fetchone()
        assert stored[0] and stored[0] != secret and len(stored[0]) == 64
        assert stored[1] == "auto"

        listed = client.get("/api/collab/screens", headers=admin)
        assert listed.status_code == 200, listed.text
        body = listed.json()
        assert body["total"] >= 1
        assert all("secret" not in item for item in body["items"])
        assert secret not in listed.text


def test_heartbeat_and_leave_require_screen_secret(tmp_path):
    with _client(tmp_path) as client:
        admin = _headers(client)
        created = _register(client, name="受保护大屏")
        screen_id, secret = created["screen_id"], created["screen_secret"]

        assert client.post(
            f"/api/public/collab/screens/{screen_id}/heartbeat", json={}
        ).status_code == 403
        assert client.post(
            f"/api/public/collab/screens/{screen_id}/heartbeat",
            json={},
            headers={"X-Screen-Secret": "wrong"},
        ).status_code == 403
        assert client.post(
            "/api/public/collab/screens/screen-missing/heartbeat",
            headers={"X-Screen-Secret": secret},
        ).status_code == 404

        beat = client.post(
            f"/api/public/collab/screens/{screen_id}/heartbeat",
            json={"floor_id": "f2"},
            headers={"X-Screen-Secret": secret},
        )
        assert beat.status_code == 200, beat.text
        assert beat.json() == {"ok": True}

        left = client.post(
            f"/api/public/collab/screens/{screen_id}/leave",
            headers={"X-Screen-Secret": secret},
        )
        assert left.status_code == 204, left.text
        left_again = client.post(
            f"/api/public/collab/screens/{screen_id}/leave",
            headers={"X-Screen-Secret": secret},
        )
        assert left_again.status_code == 204, "离线接口需幂等"

        online = {
            item["screen_id"]: item["online"]
            for item in client.get("/api/collab/screens", headers=admin).json()["items"]
        }
        assert online[screen_id] is False


def test_draft_publish_cas_and_public_projection(tmp_path):
    with _client(tmp_path) as client:
        admin = _headers(client)
        screen_id = _register(client, name="配置大屏")["screen_id"]

        saved = client.patch(
            f"/api/collab/screens/{screen_id}",
            json={
                "config": {
                    "layout_type": "grid",
                    "theme": "dark",
                    "resolution": "1920x1080",
                    "team_id": "team-1",
                }
            },
            headers=admin,
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["config_version"] == 1
        assert saved.json()["config"]["theme"] == "dark"
        assert client.get("/api/collab/screens", headers=admin).json()["items"][0][
            "source"
        ] == "manual"

        before = client.get(f"/api/public/collab/screens/{screen_id}/config")
        assert before.status_code == 200, before.text
        assert before.json()["published"] is False
        assert "team_id" not in before.json()

        published = client.post(
            f"/api/collab/screens/{screen_id}/publish",
            json={"expected_config_version": 1},
            headers=admin,
        )
        assert published.status_code == 200, published.text
        assert published.json()["config_version"] == 2

        stale = client.post(
            f"/api/collab/screens/{screen_id}/publish",
            json={"expected_config_version": 1},
            headers=admin,
        )
        assert stale.status_code == 409, stale.text
        assert stale.json()["error_code"] == "version_conflict"

        public = client.get(f"/api/public/collab/screens/{screen_id}/config").json()
        assert public["published"] is True
        assert public["config_version"] == 2
        assert public["layout_type"] == "grid"
        assert public["team_bound"] is True
        assert "team_id" not in public

        bad_grid = client.patch(
            f"/api/collab/screens/{screen_id}",
            json={"config": {"layout_type": "grid"}},
            headers=admin,
        )
        assert bad_grid.status_code == 422, bad_grid.text

        empty = _register(client, name="空布局")["screen_id"]
        cannot = client.post(
            f"/api/collab/screens/{empty}/publish",
            json={"expected_config_version": 1},
            headers=admin,
        )
        assert cannot.status_code == 422, cannot.text


def test_focus_and_delete_state_guards(tmp_path):
    with _client(tmp_path) as client:
        admin = _headers(client)
        screen_id = _register(client, name="可删除大屏")["screen_id"]
        secret = _register(client, name="另一块")["screen_secret"]

        assert client.post(
            "/api/collab/screens/screen-missing/focus",
            json={"floor_id": "f1"},
            headers=admin,
        ).status_code == 404
        assert client.post(
            f"/api/collab/screens/{screen_id}/focus",
            json={"seat_id": "s1"},
            headers=admin,
        ).status_code == 422

        focus = client.post(
            f"/api/collab/screens/{screen_id}/focus",
            json={"floor_id": "f1", "seat_id": "s1"},
            headers=admin,
        )
        assert focus.status_code == 204, focus.text

        online_delete = client.delete(
            f"/api/collab/screens/{screen_id}", headers=admin
        )
        assert online_delete.status_code == 409, online_delete.text

        left = client.post(
            f"/api/public/collab/screens/{screen_id}/leave",
            headers={"X-Screen-Secret": secret},
        )
        assert left.status_code == 403, "另一块大屏的密钥不能下线本屏"

        with closing(sqlite3.connect(tmp_path / "mailbus.db")) as conn:
            conn.execute(
                "UPDATE collab_screens SET online = 0 WHERE screen_id = ?", (screen_id,)
            )
            conn.commit()
        assert client.post(
            f"/api/collab/screens/{screen_id}/focus",
            json={"floor_id": "f1"},
            headers=admin,
        ).status_code == 409

        deleted = client.delete(f"/api/collab/screens/{screen_id}", headers=admin)
        assert deleted.status_code == 204, deleted.text
        assert client.delete(
            f"/api/collab/screens/{screen_id}", headers=admin
        ).status_code == 404


def test_public_layout_filters_team_and_hides_team_name(tmp_path):
    with _client(tmp_path) as client:
        admin = _headers(client)
        site = client.get("/api/public/layout", headers=admin)
        assert site.status_code == 200, site.text
        assert "team" not in site.text

        screen_id = _register(client, name="团队屏")["screen_id"]
        client.patch(
            f"/api/collab/screens/{screen_id}",
            json={
                "config": {
                    "layout_type": "grid",
                    "resolution": "1920x1080",
                    "team_id": "team-none",
                }
            },
            headers=admin,
        )
        client.post(
            f"/api/collab/screens/{screen_id}/publish",
            json={"expected_config_version": 1},
            headers=admin,
        )
        filtered = client.get(f"/api/public/layout?screen_id={screen_id}")
        assert filtered.status_code == 200, filtered.text
        for floor in filtered.json()["floors"]:
            for room in floor["rooms"]:
                for seat in room["seats"]:
                    assert seat["agent"] is None
        assert "team" not in filtered.text
        assert client.get("/api/public/layout?screen_id=screen-missing").status_code == 404
