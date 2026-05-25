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
from lib.utils import _now_iso, clear_json_cache
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
        """超过 max_messages → 归档溢出部分（保留 max_messages//2 条）"""
        msgs = [self._make_msg(f"msg-arch-count-{i}", MsgStatus.ACKNOWLEDGED) for i in range(5)]
        self._write_inbox(msgs)
        clear_json_cache()
        count = archive_agent(self.data_dir, "agent_a", archive_days=7, max_messages=3)
        # 5 条全 acknowledged，超过 3 条上限 → 溢出 4 条归档，保留 3//2=1 条
        assert count == 4, f"预期归档 4 条，得到 {count}"
        data = self._read_inbox()
        assert len(data["messages"]) == 1, "inbox 应保留 1 条"
    
    def test_archive_keeps_pending(self):
        """pending 状态的消息永远不会被归档，即使 overflow"""
        clear_json_cache()
        pending = self._make_msg("msg-pending1", MsgStatus.PENDING)
        acked = self._make_msg("msg-acked1", MsgStatus.ACKNOWLEDGED)
        self._write_inbox([pending, acked])
        count = archive_agent(self.data_dir, "agent_a", archive_days=7, max_messages=1)
        # 2 条消息 > max_messages=1 → 触发归档。但只有 1 条 acked，保留至少 1 条 → 不归档
        assert count == 0, f"预期归档 0 条，得到 {count}"
        data = self._read_inbox()
        assert len(data["messages"]) == 2
        # 再多一条 overflow 时才会归档 acked 消息
        more_acked = [self._make_msg(f"msg-extra-{i}", MsgStatus.ACKNOWLEDGED) for i in range(3)]
        self._write_inbox([pending] + more_acked)
        clear_json_cache()
        count2 = archive_agent(self.data_dir, "agent_a", archive_days=7, max_messages=1)
        assert count2 == 2, f"预期归档 2 条，得到 {count2}"  # 3 acked - 1 keep = 2 archived
        data2 = self._read_inbox()
        assert data2["messages"][0]["id"] == "msg-pending1"
    
    def test_archive_creates_archive_file(self):
        """归档后 archive/ 目录下应有文件（至少保留 1 条 acked）"""
        self._clean_archive()
        msgs = [self._make_msg(f"msg-arch-file-{i}", MsgStatus.ACKNOWLEDGED) for i in range(3)]
        self._write_inbox(msgs)
        archive_agent(self.data_dir, "agent_a", archive_days=7, max_messages=1)
        archive_dir = f"{self.data_dir}/archive/agent_a"
        files = os.listdir(archive_dir)
        assert len(files) > 0, "归档目录应有文件"
        with open(f"{archive_dir}/{files[0]}") as f:
            lines = f.readlines()
        # 3 条全 acked，max_messages=1 → 保留 1 条，归档 2 条
        assert len(lines) == 2, f"预期 2 条归档记录，得到 {len(lines)}"
    
    def test_archive_all(self):
        """archive_all 处理所有 agent"""
        self._clean_archive()
        os.makedirs(f"{self.data_dir}/inbox/agent_b", exist_ok=True)
        os.makedirs(f"{self.data_dir}/archive/agent_b", exist_ok=True)
        # 每个 agent 给 5 条 acked，max_messages=3 → 各归档 4 条（保留 1）
        msgs_a = [self._make_msg(f"msg-all-a-{i}", MsgStatus.ACKNOWLEDGED) for i in range(5)]
        self._write_inbox(msgs_a)
        msgs_b = [self._make_msg(f"msg-all-b-{i}", MsgStatus.ACKNOWLEDGED) for i in range(5)]
        path_b = f"{self.data_dir}/inbox/agent_b/inbox.json"
        with open(path_b, "w") as f:
            json.dump({"agent": "agent_b", "has_unread": False, "messages": msgs_b, "since": _now_iso()}, f)
        results = archive_all(self.data_dir, {"agent_a": {}, "agent_b": {}}, archive_days=7, max_messages=3)
        assert "agent_a" in results
        assert "agent_b" in results
        assert results["agent_a"] == 4, f"agent_a 预期 4，得到 {results.get('agent_a')}"
        assert results["agent_b"] == 4, f"agent_b 预期 4，得到 {results.get('agent_b')}"


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
