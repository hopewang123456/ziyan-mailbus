"""离线语义：offline 只是心跳超时（在勤离席），不剥夺能力、不打断事件流。

回归 covers：
1. 巡检不把运维入口（超管）误标离线，也不误伤从未心跳的账号；
2. offline 账号仍可读取总览与操作日志，能力不因离席失效；
3. offline 账号的运营事件流照常推送，不再因权限判定抛错中断；
4. 快照在流中途失去日志权限时降级为无日志，避免 response already started。
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import timedelta

from fastapi.testclient import TestClient

from mailbus.api import sse
from mailbus.bootstrap.main import create_app
from mailbus.bootstrap.settings import Settings
from mailbus.core.identity.values import EmployeeStatus


def _client(tmp_path) -> TestClient:
    return TestClient(create_app(Settings(data_dir=tmp_path)))


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bootstrap(client: TestClient) -> dict:
    response = client.post(
        "/api/identity/bootstrap/super-admin", json={"display_name": "超级管理员"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _offline_staff_token(client: TestClient, admin_token: str) -> str:
    """签发一张带 log_read 的邀请码，建号后推到离线，返回该员工 token。"""
    invite = client.post(
        "/api/identity/invites",
        json={"account_type": "human", "capabilities": ["log_read"], "data_scope": "global"},
        headers=_headers(admin_token),
    )
    assert invite.status_code == 201, invite.text
    applied = client.post(
        "/api/identity/staff",
        json={
            "display_name": "离席员工",
            "account_type": "human",
            "invite_code": invite.json()["invite_code"],
        },
    )
    assert applied.status_code == 201, applied.text
    token = applied.json()["token"]

    container = client.app.state.container
    cutoff = container.clock.now() + timedelta(seconds=1)
    assert container.identity.staff.mark_stale_offline(cutoff) == 1
    return token


def test_sweep_skips_super_admin_without_attendance_duty(tmp_path):
    """超管是运维入口，不参与在勤考核，不应被巡检标离线。"""
    with _client(tmp_path) as client:
        admin = _bootstrap(client)
        container = client.app.state.container
        far_cutoff = container.clock.now() + timedelta(days=1)

        assert container.identity.staff.mark_stale_offline(far_cutoff) == 0
        me = client.get("/api/identity/me", headers=_headers(admin["token"])).json()
        assert me["status"] == "active"


def test_offline_account_keeps_read_capabilities(tmp_path):
    """离线只代表心跳超时，读取总览与操作日志仍应放行。"""
    with _client(tmp_path) as client:
        admin = _bootstrap(client)
        token = _offline_staff_token(client, admin["token"])

        me = client.get("/api/identity/me", headers=_headers(token)).json()
        assert me["status"] == "offline"
        assert client.get("/api/overview", headers=_headers(token)).status_code == 200
        assert client.get("/api/log", headers=_headers(token)).status_code == 200


def test_event_stream_serves_offline_actor(tmp_path):
    """离线账号的事件流首帧应正常推送，而不是 200 后抛错断流。"""
    with _client(tmp_path) as client:
        admin = _bootstrap(client)
        token = _offline_staff_token(client, admin["token"])

        container = client.app.state.container
        actor = container.identity.sessions.resolve(token)
        assert actor.status is EmployeeStatus.OFFLINE

        async def first_chunk() -> str:
            stream = sse.event_stream(container, actor, interval=3600)
            try:
                return await anext(stream)
            finally:
                await stream.aclose()

        chunk = asyncio.run(first_chunk())
        assert chunk.startswith("data: ")
        assert '"overview"' in chunk and '"log"' in chunk


def test_snapshot_degrades_when_log_read_is_denied(tmp_path):
    """流已开始后权限失效：快照降级为无日志，不得向上抛异常。"""
    with _client(tmp_path) as client:
        admin = _bootstrap(client)
        container = client.app.state.container
        actor = container.identity.sessions.resolve(admin["token"])

        degraded = replace(actor, status=EmployeeStatus.PENDING)
        payload = sse.snapshot(container, degraded)

        assert payload["log"] == []
        assert "overview" in payload
