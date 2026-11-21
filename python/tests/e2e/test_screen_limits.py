"""公开大屏登记：数量上限与按 IP 限流。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from mailbus.adapters.system.rate_limit import RateLimiter
from mailbus.bootstrap.main import create_app
from mailbus.bootstrap.settings import Settings


def test_rate_limiter_sliding_window() -> None:
    limiter = RateLimiter(max_events=2, window_sec=10.0)
    assert limiter.allow("ip", now=0.0) is True
    assert limiter.allow("ip", now=1.0) is True
    assert limiter.allow("ip", now=2.0) is False
    assert limiter.allow("ip", now=11.0) is True
    assert limiter.allow("other", now=11.0) is True


def _payload(screen_id: str, name: str = "大屏") -> dict:
    return {"screen_id": screen_id, "name": name, "floor_id": None, "seat_id": None}


def test_public_screen_count_limit_and_idempotent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(Settings(data_dir=Path(tmp), public_screen_limit=1))
        with TestClient(app) as client:
            assert client.post("/api/public/collab/screens", json=_payload("s1")).status_code == 201
            # 已存在的编号幂等返回，不占新额度，也不覆盖名称
            again = client.post(
                "/api/public/collab/screens", json=_payload("s1", "篡改")
            )
            assert again.status_code == 201, again.text
            assert again.json()["name"] == "大屏"
            full = client.post("/api/public/collab/screens", json=_payload("s2"))
            assert full.status_code == 503, full.text
            assert full.json()["error_code"] == "capacity_exceeded"


def test_public_screen_register_rate_limited() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with TestClient(create_app(Settings(data_dir=Path(tmp)))) as client:
            for index in range(10):
                resp = client.post(
                    "/api/public/collab/screens", json=_payload(f"rate-{index}")
                )
                assert resp.status_code == 201, resp.text
            blocked = client.post("/api/public/collab/screens", json=_payload("rate-full"))
            assert blocked.status_code == 429, blocked.text
            assert blocked.json()["error_code"] == "rate_limited"
