"""
ziyan-mailbus 测试 — scanner 模块
"""

import os
import sys
import json
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.models import Message, Inbox, MsgStatus, Priority, MsgType
from lib.utils import resolve_paths, _now_iso, clear_json_cache
from lib.scanner import scan_all, build_queues, mark_as_pushed, update_message_status


class TestScanner:
    @classmethod
    def setup_class(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="mailbus_test_scanner_")
        cls.data_dir = f"{cls.tmpdir}/store"
        os.makedirs(f"{cls.data_dir}/inbox/agent_a", exist_ok=True)
        os.makedirs(f"{cls.data_dir}/inbox/agent_b", exist_ok=True)
        os.makedirs(f"{cls.data_dir}/queue/urgent", exist_ok=True)
        os.makedirs(f"{cls.data_dir}/queue/normal", exist_ok=True)
        os.makedirs(f"{cls.data_dir}/errors", exist_ok=True)
        cls.agents = {"agent_a": {}, "agent_b": {}}
        clear_json_cache()  # 确保全局缓存干净
    
    @classmethod
    def teardown_class(cls):
        shutil.rmtree(cls.tmpdir)
    
    def _write_inbox(self, agent: str, inbox: Inbox):
        path = f"{self.data_dir}/inbox/{agent}/inbox.json"
        clear_json_cache()  # 直接写文件会绕过 json_write 的缓存清除，手动清理
        with open(path, "w") as f:
            json.dump(inbox.to_dict(), f, ensure_ascii=False)
    
    def _read_inbox(self, agent: str) -> Inbox:
        path = f"{self.data_dir}/inbox/{agent}/inbox.json"
        with open(path) as f:
            return Inbox.from_dict(json.load(f))
    
    def _make_msg(self, msg_id: str, status=MsgStatus.PENDING, priority=Priority.NORMAL):
        return {
            "id": msg_id,
            "from": "test",
            "to": "agent_a",
            "priority": priority,
            "type": MsgType.TASK,
            "content": f"test message {msg_id}",
            "attachments": [],
            "reply_format": {},
            "action": {"ack": True, "reply_to": None, "execute": True, "forward_to": []},
            "status": status,
            "pushed_count": 0,
            "created_at": _now_iso(),
            "acknowledged_at": None,
        }

    # ── 测试用例 ──
    
    def test_scan_empty_inbox(self):
        """空 inbox → 返回空列表"""
        inbox = Inbox(agent="agent_a", has_unread=False, messages=[])
        self._write_inbox("agent_a", inbox)
        inbox = Inbox(agent="agent_b", has_unread=False, messages=[])
        self._write_inbox("agent_b", inbox)
        result = scan_all(self.data_dir, self.agents)
        assert result == [], f"预期空列表，得到 {result}"
    
    def test_scan_all_pending(self):
        """有 pending 消息 → 按优先级分类返回"""
        msg1 = self._make_msg("msg-001", MsgStatus.PENDING, Priority.NORMAL)
        msg2 = self._make_msg("msg-002", MsgStatus.PENDING, Priority.URGENT)
        inbox = Inbox(agent="agent_a", has_unread=True, messages=[msg1, msg2])
        self._write_inbox("agent_a", inbox)
        result = scan_all(self.data_dir, {"agent_a": {}})
        assert len(result) == 1, f"预期 1 项，得到 {len(result)}"
        name, urgent, normal = result[0]
        assert name == "agent_a"
        assert len(urgent) == 1 and urgent[0].id == "msg-002"
        assert len(normal) == 1 and normal[0].id == "msg-001"
    
    def test_scan_skip_acked(self):
        """非 pending 状态的消息跳过"""
        msg1 = self._make_msg("msg-003", MsgStatus.ACKNOWLEDGED, Priority.NORMAL)
        msg2 = self._make_msg("msg-004", MsgStatus.FAILED, Priority.NORMAL)
        inbox = Inbox(agent="agent_a", has_unread=True, messages=[msg1, msg2])
        self._write_inbox("agent_a", inbox)
        result = scan_all(self.data_dir, {"agent_a": {}})
        assert result == [], f"预期空（无 pending），得到 {result}"
    
    def test_scan_urgent_first(self):
        """加急 agent 排前面"""
        msg_a = self._make_msg("msg-a1", MsgStatus.PENDING, Priority.NORMAL)
        inbox_a = Inbox(agent="agent_a", has_unread=True, messages=[msg_a])
        self._write_inbox("agent_a", inbox_a)
        msg_b = self._make_msg("msg-b1", MsgStatus.PENDING, Priority.URGENT)
        inbox_b = Inbox(agent="agent_b", has_unread=True, messages=[msg_b])
        self._write_inbox("agent_b", inbox_b)
        result = scan_all(self.data_dir, {"agent_a": {}, "agent_b": {}})
        assert len(result) == 2
        # agent_b 有加急，应该在前面
        assert result[0][0] == "agent_b", f"加急 agent 应在前，得到 {result[0][0]}"
        assert result[1][0] == "agent_a"
    
    def test_build_queues(self):
        """build_queues 正确构建两个队列"""
        msg1 = self._make_msg("msg-q1", MsgStatus.PENDING, Priority.URGENT)
        msg2 = self._make_msg("msg-q2", MsgStatus.PENDING, Priority.NORMAL)
        inbox = Inbox(agent="agent_a", has_unread=True, messages=[msg1, msg2])
        self._write_inbox("agent_a", inbox)
        urgent, normal = build_queues(self.data_dir, {"agent_a": {}})
        assert "agent_a" in urgent
        assert len(urgent["agent_a"]) == 1
        # P2 串行约束：有加急时只推加急，普通排队
        assert "agent_a" not in normal
    
    def test_mark_as_pushed(self):
        """mark_as_pushed 正确修改状态"""
        msg1 = self._make_msg("msg-p1", MsgStatus.PENDING)
        inbox = Inbox(agent="agent_a", has_unread=True, messages=[msg1])
        self._write_inbox("agent_a", inbox)
        mark_as_pushed(self.data_dir, "agent_a", ["msg-p1"])
        inbox = self._read_inbox("agent_a")
        found = False
        for m in inbox.messages:
            mid = m.id if hasattr(m, 'id') else (m["id"] if isinstance(m, dict) else None)
            mstatus = m.status if hasattr(m, 'status') else (m["status"] if isinstance(m, dict) else None)
            if mid == "msg-p1" and mstatus == MsgStatus.PUSHED:
                found = True
                break
        assert found, "消息状态应变为 pushed"
    
    def test_update_message_status(self):
        """update_message_status 正确更新单条消息"""
        msg1 = self._make_msg("msg-u1", MsgStatus.PUSHED)
        inbox = Inbox(agent="agent_a", has_unread=True, messages=[msg1])
        self._write_inbox("agent_a", inbox)
        update_message_status(self.data_dir, "agent_a", "msg-u1", MsgStatus.ACKNOWLEDGED)
        inbox = self._read_inbox("agent_a")
        found = False
        for m in inbox.messages:
            mid = m.id if hasattr(m, 'id') else (m["id"] if isinstance(m, dict) else None)
            mstatus = m.status if hasattr(m, 'status') else (m["status"] if isinstance(m, dict) else None)
            if mid == "msg-u1" and mstatus == MsgStatus.ACKNOWLEDGED:
                found = True
                break
        assert found, "消息状态应变为 acknowledged"
    
    def test_update_nonexistent_msg(self):
        """更新不存在的消息 → 返回 False"""
        result = update_message_status(self.data_dir, "agent_a", "msg-nonexist", MsgStatus.ACKNOWLEDGED)
        assert result is False


if __name__ == "__main__":
    t = TestScanner()
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
