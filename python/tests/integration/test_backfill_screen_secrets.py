"""回填脚本：为存量 NULL 密钥的大屏补发密钥（幂等）。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from mailbus.adapters.persistence.sqlite.connection import connect
from mailbus.adapters.persistence.sqlite.migrations import apply_migrations

_TOOL = Path(__file__).resolve().parents[2] / "tools" / "backfill_screen_secrets.py"
_INSERT = (
    "INSERT INTO collab_screens"
    " (screen_id, name, floor_id, seat_id, online, last_seen_at, created_at, secret)"
    " VALUES (?, ?, NULL, NULL, 1, NULL, ?, ?)"
)


def _load_tool():
    spec = importlib.util.spec_from_file_location("backfill_screen_secrets", _TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _seed(tmp_path: Path) -> None:
    conn = connect(tmp_path / "mailbus.db")
    try:
        apply_migrations(conn)
        conn.execute(_INSERT, ("legacy-a", "存量 A", 1.0, None))
        conn.execute(_INSERT, ("legacy-b", "存量 B", 2.0, ""))
        conn.execute(_INSERT, ("secured-c", "已有密钥 C", 3.0, "keep-me"))
    finally:
        conn.close()


def _secrets(tmp_path: Path) -> dict[str, str | None]:
    conn = connect(tmp_path / "mailbus.db")
    try:
        rows = conn.execute("SELECT screen_id, secret FROM collab_screens").fetchall()
    finally:
        conn.close()
    return {row["screen_id"]: row["secret"] for row in rows}


def test_backfill_fills_missing_secret_and_is_idempotent(tmp_path, capsys):
    _seed(tmp_path)
    tool = _load_tool()

    assert tool.main(["--data-dir", str(tmp_path)]) == 0
    first = _secrets(tmp_path)
    assert first["legacy-a"]
    assert first["legacy-b"]
    assert first["legacy-a"] != first["legacy-b"]
    assert first["secured-c"] == "keep-me"  # 已有密钥不得被覆盖

    # 第二次运行不产生任何变更
    assert tool.main(["--data-dir", str(tmp_path)]) == 0
    assert _secrets(tmp_path) == first
    assert "无需回填" in capsys.readouterr().out


def test_backfill_dry_run_does_not_write(tmp_path):
    _seed(tmp_path)
    tool = _load_tool()

    assert tool.main(["--data-dir", str(tmp_path), "--dry-run"]) == 0
    after = _secrets(tmp_path)
    assert after["legacy-a"] is None
    assert after["legacy-b"] == ""


def test_backfill_reports_missing_database(tmp_path):
    tool = _load_tool()
    missing = tmp_path / "nope"
    assert tool.main(["--data-dir", str(missing)]) == 1


def test_backfill_via_api_keeps_secrets_and_exports(tmp_path, monkeypatch):
    """管理员登记接口对已有大屏保留原密钥，结果导出到文件。"""
    tool = _load_tool()
    screens = [
        {"screen_id": "a", "name": "A", "floor_id": "f1", "seat_id": None, "online": False},
        {"screen_id": "b", "name": "B", "floor_id": None, "seat_id": "s9", "online": True},
    ]
    secrets_by_id = {"a": "s-a", "b": "s-b"}
    calls: list[tuple[str, str, dict | None]] = []

    def fake_request(base_url, token, method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET":
            return 200, screens
        assert method == "POST" and path == "/api/collab/screens"
        return 201, {
            "screen_id": payload["screen_id"],
            "name": payload["name"],
            "secret": secrets_by_id[payload["screen_id"]],
        }

    monkeypatch.setattr(tool, "_request", fake_request)
    out = tmp_path / "keys.json"

    rc = tool.main(
        [
            "--via-api",
            "--token",
            "t",
            "--base-url",
            "http://example",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    exported = json.loads(out.read_text(encoding="utf-8"))
    assert {e["screen_id"]: e["secret"] for e in exported["screens"]} == secrets_by_id
    # 登记请求沿用原归属字段，未额外调用公开 leave
    posts = [c for c in calls if c[0] == "POST"]
    assert [p[2]["screen_id"] for p in posts] == ["a", "b"]
    assert posts[0][2]["floor_id"] == "f1"
    assert posts[1][2]["seat_id"] == "s9"


def test_backfill_via_api_requires_token(tmp_path):
    tool = _load_tool()
    assert tool.main(["--via-api", "--out", str(tmp_path / "k.json")]) == 2


def test_backfill_via_api_dry_run_makes_no_register_calls(tmp_path, monkeypatch):
    tool = _load_tool()
    calls: list[str] = []

    def fake_request(base_url, token, method, path, payload=None):
        calls.append(method)
        return 200, [{"screen_id": "a", "name": "A"}]

    monkeypatch.setattr(tool, "_request", fake_request)
    rc = tool.main(
        ["--via-api", "--token", "t", "--dry-run", "--out", str(tmp_path / "k.json")]
    )
    assert rc == 0
    assert calls == ["GET"]
    assert not (tmp_path / "k.json").exists()
