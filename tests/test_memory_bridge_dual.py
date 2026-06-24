"""memory-bridge 双写单元测试。"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.memory_bridge import (  # noqa: E402
    collect_pending_messages,
    load_sync_marker,
    run_bridge,
    save_sync_marker,
    write_memory_to_sqlite,
)

class TestSyncMarker(unittest.TestCase):
    def test_v1_array_migration(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "sync_to_memory.json"
            f.write_text(json.dumps(["msg-1", "msg-2"]), encoding="utf-8")
            m = load_sync_marker(f)
            self.assertEqual(m["agentmemory"], {"msg-1", "msg-2"})
            self.assertEqual(m["sqlite"], set())

    def test_v2_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "sync_to_memory.json"
            save_sync_marker(f, {"a"}, {"b"})
            m = load_sync_marker(f)
            self.assertEqual(m["sqlite"], {"a"})
            self.assertEqual(m["agentmemory"], {"b"})


class TestDualWriteBridge(unittest.TestCase):
    def _setup_inbox(self, data_dir: str, agent: str, msg_id: str, status: str = "acknowledged"):
        inbox_dir = Path(data_dir) / "inbox" / agent
        inbox_dir.mkdir(parents=True, exist_ok=True)
        inbox = {
            "messages": [{
                "id": msg_id,
                "status": status,
                "content": "hello from test",
                "from": "lingzhao",
                "type": "notice",
            }]
        }
        (inbox_dir / "inbox.json").write_text(json.dumps(inbox), encoding="utf-8")

    def test_sqlite_writes_when_agentmemory_down(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "team-memory.db")
            os.environ["TEAM_MEMORY_DB"] = db_path
            os.environ["MEMORY_BRIDGE_SQLITE"] = "1"
            os.environ["MEMORY_BRIDGE_AGENTMEMORY"] = "1"
            self._setup_inbox(td, "dali", "test-msg-001")

            with patch("lib.memory_bridge.agentmemory_healthy", return_value=False):
                stats = run_bridge(td, limit=10, url="http://127.0.0.1:9")

            self.assertEqual(stats["sqlite_ok"], 1)
            self.assertEqual(stats["agentmemory_skip"], 1)

            marker = load_sync_marker(Path(td) / "inbox" / "dali" / "sync_to_memory.json")
            self.assertIn("test-msg-001", marker["sqlite"])
            self.assertNotIn("test-msg-001", marker["agentmemory"])

            import sqlite3
            conn = sqlite3.connect(db_path)
            row = conn.execute(
                "SELECT key FROM memories WHERE key=?", ("mailbus:test-msg-001",)
            ).fetchone()
            conn.close()
            self.assertIsNotNone(row)

    def test_agentmemory_writes_when_healthy(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "team-memory.db")
            os.environ["TEAM_MEMORY_DB"] = db_path
            os.environ["MEMORY_BRIDGE_SQLITE"] = "1"
            os.environ["MEMORY_BRIDGE_AGENTMEMORY"] = "1"
            self._setup_inbox(td, "dali", "test-msg-002")

            def fake_am(*args, **kwargs):
                return {"success": True}

            with patch("lib.memory_bridge.agentmemory_healthy", return_value=True):
                with patch("lib.memory_bridge.write_memory_to_agentmemory", side_effect=fake_am):
                    stats = run_bridge(td, limit=10)

            self.assertEqual(stats["sqlite_ok"], 1)
            self.assertEqual(stats["agentmemory_ok"], 1)
            marker = load_sync_marker(Path(td) / "inbox" / "dali" / "sync_to_memory.json")
            self.assertIn("test-msg-002", marker["sqlite"])
            self.assertIn("test-msg-002", marker["agentmemory"])

    def test_idempotent_sqlite_key(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "mem.db")
            os.environ["TEAM_MEMORY_DB"] = db_path
            ok1 = write_memory_to_sqlite("dali", "same-id", "content v1", "a", "notice")
            ok2 = write_memory_to_sqlite("dali", "same-id", "content v2", "a", "notice")
            self.assertTrue(ok1 and ok2)
            import sqlite3
            conn = sqlite3.connect(db_path)
            count = conn.execute("SELECT COUNT(*) FROM memories WHERE key=?", ("mailbus:same-id",)).fetchone()[0]
            content = conn.execute("SELECT content FROM memories WHERE key=?", ("mailbus:same-id",)).fetchone()[0]
            conn.close()
            self.assertEqual(count, 1)
            self.assertIn("content v2", content)

    def test_v1_marker_sqlite_backfill(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = os.path.join(td, "team-memory.db")
            os.environ["TEAM_MEMORY_DB"] = db_path
            os.environ["MEMORY_BRIDGE_SQLITE"] = "1"
            os.environ["MEMORY_BRIDGE_AGENTMEMORY"] = "0"
            agent_dir = Path(td) / "inbox" / "dali"
            agent_dir.mkdir(parents=True)
            (agent_dir / "sync_to_memory.json").write_text(json.dumps(["old-am-only"]), encoding="utf-8")
            self._setup_inbox(td, "dali", "backfill-001")

            stats = run_bridge(td, limit=10)
            self.assertEqual(stats["sqlite_ok"], 1)
            marker = load_sync_marker(agent_dir / "sync_to_memory.json")
            self.assertIn("backfill-001", marker["sqlite"])
            self.assertIn("old-am-only", marker["agentmemory"])


class TestCollectPending(unittest.TestCase):
    def test_skips_non_acknowledged(self):
        with tempfile.TemporaryDirectory() as td:
            inbox_dir = Path(td) / "inbox" / "dali"
            inbox_dir.mkdir(parents=True)
            (inbox_dir / "inbox.json").write_text(json.dumps({
                "messages": [{"id": "x", "status": "pending", "content": "hi", "from": "a"}]
            }), encoding="utf-8")
            msgs, _ = collect_pending_messages(td)
            self.assertEqual(len(msgs), 0)


if __name__ == "__main__":
    unittest.main()
