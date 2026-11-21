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
        secret = created.json()["secret"]
        assert secret  # M14：新建大屏回显一次性密钥

        beat = client.post(
            "/api/public/collab/screens/screen-ab12/heartbeat",
            json={"floor_id": "f2", "seat_id": None, "secret": secret},
        )
        assert beat.status_code == 200, beat.text
        assert beat.json() == {"ok": True}

        listed = client.get("/api/collab/screens", headers=headers)
        assert listed.status_code == 200, listed.text
        assert listed.json()[0]["screen_id"] == "screen-ab12"
        assert listed.json()[0]["floor_id"] == "f2"
        assert listed.json()[0].get("secret") is None  # 列表不泄露密钥

        # 公开重复登记是幂等的，不允许匿名覆盖既有名称与归属，且不回显密钥
        overwrite = client.post(
            "/api/public/collab/screens",
            json={"screen_id": "screen-ab12", "name": "篡改名称", "floor_id": "f9"},
        )
        assert overwrite.status_code == 201, overwrite.text
        assert overwrite.json()["name"] == "大屏 ab12"
        assert overwrite.json()["floor_id"] == "f2"
        assert overwrite.json().get("secret") is None

        focus = client.post(
            "/api/collab/screens/screen-ab12/focus",
            json={"floor_id": "f2", "seat_id": None},
            headers=headers,
        )
        assert focus.status_code == 204, focus.text

        left = client.post(
            "/api/public/collab/screens/screen-ab12/leave",
            json={"secret": secret},
        )
        assert left.status_code == 204, left.text
        offline = client.get("/api/collab/screens", headers=headers).json()[0]
        assert offline["online"] is False


def test_public_heartbeat_and_leave_require_secret(tmp_path):
    """M14：未持有密钥的匿名调用不能篡改已知大屏的归属或离线状态。"""
    with _client(tmp_path) as client:
        _bootstrap(client)
        created = client.post(
            "/api/public/collab/screens",
            json={"screen_id": "screen-sec", "name": "受保护大屏"},
        )
        assert created.status_code == 201, created.text
        secret = created.json()["secret"]
        assert secret

        no_secret = client.post(
            "/api/public/collab/screens/screen-sec/heartbeat",
            json={"floor_id": "hacked"},
        )
        assert no_secret.status_code == 403, no_secret.text

        wrong_secret = client.post(
            "/api/public/collab/screens/screen-sec/heartbeat",
            json={"secret": "wrong-key"},
        )
        assert wrong_secret.status_code == 403, wrong_secret.text

        leave_no_secret = client.post(
            "/api/public/collab/screens/screen-sec/leave"
        )
        assert leave_no_secret.status_code == 403, leave_no_secret.text

        ok = client.post(
            "/api/public/collab/screens/screen-sec/heartbeat",
            json={"secret": secret, "floor_id": "f3"},
        )
        assert ok.status_code == 200, ok.text

        gone = client.post(
            "/api/public/collab/screens/screen-sec/leave", json={"secret": secret}
        )
        assert gone.status_code == 204, gone.text


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


def test_admin_can_force_offline_without_secret(tmp_path):
    """管理端可免密钥下线他人大屏；普通员工无权强制下线。"""
    with _client(tmp_path) as client:
        headers = _bootstrap(client)
        created = client.post(
            "/api/public/collab/screens",
            json={"screen_id": "screen-force", "name": "强制离线"},
        )
        assert created.status_code == 201, created.text
        assert created.json()["secret"]

        left = client.post("/api/collab/screens/screen-force/leave", headers=headers)
        assert left.status_code == 204, left.text
        listed = client.get("/api/collab/screens", headers=headers).json()
        assert listed[0]["online"] is False

        invite = client.post(
            "/api/identity/invites",
            json={"account_type": "human", "capabilities": []},
            headers=headers,
        ).json()
        applied = client.post(
            "/api/identity/staff",
            json={
                "display_name": "普通员工",
                "account_type": "human",
                "invite_code": invite["invite_code"],
            },
        ).json()
        plain = {"Authorization": f"Bearer {applied['token']}"}

        denied = client.post(
            "/api/collab/screens/screen-force/leave", headers=plain
        )
        assert denied.status_code == 403, denied.text


def test_public_screen_limit_counts_only_online(tmp_path):
    """公开大屏上限只统计在线记录，历史离线屏不占用名额。"""
    import sqlite3
    import time

    with _client(tmp_path) as client:
        now = time.time()
        # 直接落库，避免触发公开登记限流
        with sqlite3.connect(tmp_path / "mailbus.db") as conn:
            conn.executemany(
                "INSERT INTO collab_screens"
                " (screen_id, name, floor_id, seat_id, online,"
                " last_seen_at, created_at, secret)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (f"bulk-{index:03d}", "批量大屏", None, None, 1, now, now, "s")
                    for index in range(64)
                ],
            )

        blocked = client.post(
            "/api/public/collab/screens",
            json={"screen_id": "bulk-over", "name": "超限大屏"},
        )
        assert blocked.status_code == 503, blocked.text

        with sqlite3.connect(tmp_path / "mailbus.db") as conn:
            conn.execute(
                "UPDATE collab_screens SET last_seen_at = ?", (now - 3600,)
            )

        allowed = client.post(
            "/api/public/collab/screens",
            json={"screen_id": "bulk-after", "name": "离线后登记"},
        )
        assert allowed.status_code == 201, allowed.text
