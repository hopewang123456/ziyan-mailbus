"""
ziyan-mailbus 测试 — archiver 模块
"""

import os
import sys
import json
import tempfile
import shutil
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.models import MsgStatus, Inbox
from lib.utils import _now_iso
from lib.archiver import archive_agent, archive_all


class TestArchiver:
    @classmethod
    def setup_class(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="mailbus_test_archive_")
        cls.data_dir = f"{cls.tmpdir}/store"
        os.makedirs(f"{cls.data_dir}/inbox/agent_a", exist_ok=True)
        os.makedirs(f"{cls.data_dir}/archive/agent_a", exist_ok=True)
        os.makedirs(f"{cls.data_dir}/errors", exist_ok=True)
        cls.agents = {"agent_a": {}}
    
    @classmethod
    def teardown_class(cls):
        shutil.rmtree(cls.tmpdir)
    
    def _make_msg(self, msg_id: str, status=MsgStatus.ACKNOWLEDGED) -> dict:
        return {
            "id": msg_id,
            "from": "test",
            "to": "agent_a",
            "priority": "normal",
            "type": "notice",
            "content": f"test {msg_id}",
            "attachments": [],
            "reply_format": {},
            "status": status,
            "pushed_count": 1,
            "created_at": _now_iso(),
            "acknowledged_at": _now_iso(),
        }
    
    def _write_inbox(self, messages: list):
        path = f"{self.data_dir}/inbox/agent_a/inbox.json"
        data = {
            "agent": "agent_a",
            "has_unread": False,
            "messages": messages,
            "since": _now_iso(),
        }
        with open(path, "w") as f:
            json.dump(data, f, ensure_ascii=False)
    
    def _clean_archive(self):
        """清理归档目录（每个测试独立）"""
        archive_dir = f"{self.data_dir}/archive/agent_a"
        if os.path.isdir(archive_dir):
            shutil.rmtree(archive_dir)
        os.makedirs(archive_dir, exist_ok=True)
    
    def _read_inbox(self) -> dict:
        path = f"{self.data_dir}/inbox/agent_a/inbox.json"
        with open(path) as f:
            return json.load(f)
    
    # ── 测试用例 ──
    
    def test_no_archive_needed(self):
        """少于 300 条且消息未满 7 天 → 不归档"""
        msg = self._make_msg("msg-noarch1", MsgStatus.ACKNOWLEDGED)
        self._write_inbox([msg])
        count = archive_agent(self.data_dir, "agent_a", archive_days=7, max_messages=300)
        assert count == 0, f"预期 0，得到 {count}"
        data = self._read_inbox()
        assert len(data["messages"]) == 1
    
    def test_archive_by_count(self):
        """超过 max_messages → 归档"""
        msgs = [self._make_msg(f"msg-arch-count-{i}", MsgStatus.ACKNOWLEDGED) for i in range(5)]
        self._write_inbox(msgs)
        count = archive_agent(self.data_dir, "agent_a", archive_days=7, max_messages=3)
        # 注意：只归档 acknowledged 的，5 条全 acknowledged，超过 3 条 → 归档 5 条
        assert count == 5, f"预期归档 5 条，得到 {count}"
        data = self._read_inbox()
        assert len(data["messages"]) == 0, "inbox 应清空"
    
    def test_archive_keeps_pending(self):
        """pending 状态的消息不会被归档"""
        pending = self._make_msg("msg-pending1", MsgStatus.PENDING)
        acked = self._make_msg("msg-acked1", MsgStatus.ACKNOWLEDGED)
        self._write_inbox([pending, acked])
        count = archive_agent(self.data_dir, "agent_a", archive_days=7, max_messages=1)
        assert count == 1, f"预期归档 1 条，得到 {count}"
        data = self._read_inbox()
        assert len(data["messages"]) == 1
        assert data["messages"][0]["id"] == "msg-pending1"
    
    def test_archive_creates_archive_file(self):
        """归档后 archive/ 目录下应有文件"""
        self._clean_archive()
        msgs = [self._make_msg(f"msg-arch-file-{i}", MsgStatus.ACKNOWLEDGED) for i in range(3)]
        self._write_inbox(msgs)
        archive_agent(self.data_dir, "agent_a", archive_days=7, max_messages=1)
        archive_dir = f"{self.data_dir}/archive/agent_a"
        files = os.listdir(archive_dir)
        assert len(files) > 0, "归档目录应有文件"
        with open(f"{archive_dir}/{files[0]}") as f:
            lines = f.readlines()
        assert len(lines) == 3, f"预期 3 条归档记录，得到 {len(lines)}"
    
    def test_archive_all(self):
        """archive_all 处理所有 agent"""
        os.makedirs(f"{self.data_dir}/inbox/agent_b", exist_ok=True)
        os.makedirs(f"{self.data_dir}/archive/agent_b", exist_ok=True)
        msg_a = self._make_msg("msg-all-a", MsgStatus.ACKNOWLEDGED)
        self._write_inbox([msg_a])
        msg_b = {
            "id": "msg-all-b",
            "from": "test",
            "to": "agent_b",
            "priority": "normal",
            "type": "notice",
            "content": "test msg-all-b",
            "attachments": [],
            "reply_format": {},
            "status": MsgStatus.ACKNOWLEDGED,
            "pushed_count": 1,
            "created_at": _now_iso(),
            "acknowledged_at": _now_iso(),
        }
        path_b = f"{self.data_dir}/inbox/agent_b/inbox.json"
        with open(path_b, "w") as f:
            json.dump({"agent": "agent_b", "has_unread": False, "messages": [msg_b], "since": _now_iso()}, f)
        results = archive_all(self.data_dir, {"agent_a": {}, "agent_b": {}}, archive_days=7, max_messages=1)
        assert "agent_a" in results
        assert "agent_b" in results
        assert results["agent_a"] >= 1
        assert results["agent_b"] >= 1


if __name__ == "__main__":
    t = TestArchiver()
    t.setup_class()
    failures = []
    for name in dir(t):
        if name.startswith("test_"):
            try:
                getattr(t, name)()
                print(f"  ✓ {name}")
            except Exception as e:
                print(f"  ✗ {name}: {e}")
                failures.append(name)
    t.teardown_class()
    if failures:
        print(f"\n✗ {len(failures)} 个测试失败: {failures}")
        sys.exit(1)
    else:
        print("\n✓ 全部通过")
