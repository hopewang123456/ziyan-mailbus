"""SSE 长连接上限：管理端事件流与协同流共享同一容量闸门。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from mailbus.adapters.system.concurrency import StreamGate
from mailbus.bootstrap.main import create_app
from mailbus.bootstrap.settings import Settings


def test_stream_gate_counts_and_releases() -> None:
    gate = StreamGate(2)
    assert gate.acquire() is True
    assert gate.acquire() is True
    assert gate.full is True
    assert gate.acquire() is False
    gate.release()
    assert gate.full is False
    gate.release()
    gate.release()  # 多余释放不会让计数变负
    assert gate.active == 0


def test_all_streams_share_capacity() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(Settings(data_dir=Path(tmp), sse_max_streams=0))
        with TestClient(app) as client:
            token = client.post(
                "/api/identity/bootstrap/super-admin", json={"display_name": "超管"}
            ).json()["token"]
            headers = {"Authorization": f"Bearer {token}"}
            for path in ("/api/stream", "/api/collab/stream", "/api/public/collab/stream"):
                resp = client.get(path, headers=headers)
                assert resp.status_code == 503, (path, resp.status_code, resp.text)
                assert resp.json()["error_code"] == "capacity_exceeded"
