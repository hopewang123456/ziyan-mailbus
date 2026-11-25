"""公开大屏登记：数量上限与按 IP 限流。"""

from __future__ import annotations

import sqlite3
import tempfile
import time
from contextlib import closing
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


def _bulk_screens(tmp_path: Path, now: float) -> None:
    with closing(sqlite3.connect(tmp_path / "mailbus.db")) as conn:
        conn.executemany(
            "INSERT INTO collab_screens"
            " (screen_id, name, online, last_seen_at, created_at, secret_hash,"
            " source, config_json, published_config_json, config_version, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (f"bulk-{index:03d}", "批量大屏", 1, now, now, "hash", "auto", "{}", "{}", 1, now)
                for index in range(64)
            ],
        )
        conn.commit()


def test_public_screen_count_limit_counts_only_online() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(Settings(data_dir=Path(tmp), public_screen_limit=64))
        with TestClient(app) as client:
            now = time.time()
            _bulk_screens(Path(tmp), now)

            full = client.post(
                "/api/public/collab/screens", json={"name": "超限大屏"}
            )
            assert full.status_code == 503, full.text
            assert full.json()["error_code"] == "capacity_exceeded"

            with closing(sqlite3.connect(Path(tmp) / "mailbus.db")) as conn:
                conn.execute(
                    "UPDATE collab_screens SET online = 0, last_seen_at = ?",
                    (now - 3600,),
                )
                conn.commit()

            allowed = client.post(
                "/api/public/collab/screens", json={"name": "离线后登记"}
            )
            assert allowed.status_code == 201, allowed.text


def test_public_screen_register_rate_limited() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with TestClient(create_app(Settings(data_dir=Path(tmp)))) as client:
            for index in range(10):
                resp = client.post(
                    "/api/public/collab/screens", json={"name": f"大屏 {index}"}
                )
                assert resp.status_code == 201, resp.text
            blocked = client.post(
                "/api/public/collab/screens", json={"name": "超频大屏"}
            )
            assert blocked.status_code == 429, blocked.text
            assert blocked.json()["error_code"] == "rate_limited"
