"""
ziyan-mailbus 测试 — ack_handler 模块
"""

import os
import sys
import json
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.models import MsgStatus, Inbox
from lib.utils import resolve_paths, _now_iso
from lib.ack_handler import process_ack, process_mark_read, process_forward, scan_ack_files
from lib.utils import clear_json_cache


class TestAckHandler:
    @classmethod
    def setup_class(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="mailbus_test_ack_")
        cls.data_dir = f"{cls.tmpdir}/store"
        os.makedirs(f"{cls.data_dir}/inbox/agent_a", exist_ok=True)
        os.makedirs(f"{cls.data_dir}/inbox/agent_b", exist_ok=True)
        os.makedirs(f"{cls.data_dir}/queue/urgent", exist_ok=True)
        os.makedirs(f"{cls.data_dir}/queue/normal", exist_ok=True)
        os.makedirs(f"{cls.data_dir}/errors", exist_ok=True)
        cls.agents = {"agent_a": {}, "agent_b": {}}
    
    @classmethod
    def teardown_class(cls):
        shutil.rmtree(cls.tmpdir)
    
    def _write_inbox(self, agent: str, messages: list):
        path = f"{self.data_dir}/inbox/{agent}/inbox.json"
        has_unread = any(
            (isinstance(m, dict) and m.get("status") == MsgStatus.PENDING)
            or (not isinstance(m, dict) and m.status == MsgStatus.PENDING)
            for m in messages
        )
        data = {"agent": agent, "has_unread": has_unread, "messages": messages, "since": _now_iso()}
        with open(path, "w") as f:
            json.dump(data, f, ensure_ascii=False)
    
    def _make_msg(self, msg_id: str, status=MsgStatus.PUSHED) -> dict:
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
            "acknowledged_at": None,
        }
    
    # ── 测试用例 ──
    
    def test_process_ack(self):
        """ack 回复 → 状态改为 acknowledged"""
        msg = self._make_msg("msg-ack1", MsgStatus.PUSHED)
        self._write_inbox("agent_a", [msg])
        result = process_ack(self.data_dir, "agent_a", {
            "action": "ack", "msg_id": "msg-ack1", "agent": "agent_a", "timestamp": _now_iso()
        })
        assert result, "process_ack 应返回 True"
        path = f"{self.data_dir}/inbox/agent_a/inbox.json"
        with open(path) as f:
            data = json.load(f)
        m = next(m for m in data["messages"] if m["id"] == "msg-ack1")
        assert m["status"] == MsgStatus.ACKNOWLEDGED, f"预期 acknowledged，得到 {m['status']}"
        assert m["acknowledged_at"] is not None, "acknowledged_at 不应为 None"
    
    def test_process_ack_nonexistent(self):
        """不存在的 msg_id → 返回 False"""
        result = process_ack(self.data_dir, "agent_a", {
            "action": "ack", "msg_id": "msg-nonexist", "agent": "agent_a", "timestamp": _now_iso()
        })
        assert result is False
    
    def test_process_mark_read(self):
        """mark_read → 多条消息改为 acknowledged"""
        clear_json_cache()
        msg1 = self._make_msg("msg-mr1", MsgStatus.PUSHED)
        msg2 = self._make_msg("msg-mr2", MsgStatus.PUSHED)
        self._write_inbox("agent_a", [msg1, msg2])
        result = process_mark_read(self.data_dir, "agent_a", {
            "action": "mark_read", "msg_ids": ["msg-mr1", "msg-mr2"], "agent": "agent_a", "timestamp": _now_iso()
        })
        assert result, "process_mark_read 应返回 True"
        path = f"{self.data_dir}/inbox/agent_a/inbox.json"
        with open(path) as f:
            data = json.load(f)
        for m in data["messages"]:
            assert m["status"] == MsgStatus.ACKNOWLEDGED, f"{m['id']} 应为 acknowledged"
    
    def test_process_forward(self):
        """forward → 写入目标 agent 的 inbox"""
        result = process_forward(self.data_dir, {
            "action": "forward",
            "original_msg_id": "msg-orig1",
            "from": "agent_a",
            "to": "agent_b",
            "type": "task",
            "priority": "normal",
            "content": "请处理这个任务",
            "attachments": [],
            "timestamp": _now_iso(),
        })
        assert result, "process_forward 应返回 True"
        path = f"{self.data_dir}/inbox/agent_b/inbox.json"
        with open(path) as f:
            data = json.load(f)
        assert len(data["messages"]) == 1, f"预期 agent_b 有 1 条消息，得到 {len(data['messages'])}"
        assert data["has_unread"] is True
        m = data["messages"][0]
        assert m["content"] == "请处理这个任务"
        assert m["status"] == MsgStatus.PENDING
        assert m["priority"] == "normal"
    
    def test_process_forward_no_target(self):
        """forward 没有 to → 返回 False"""
        result = process_forward(self.data_dir, {
            "action": "forward",
            "from": "agent_a",
            "content": "无目标",
        })
        assert result is False
    
    def test_scan_ack_files(self):
        """scan_ack_files → 处理所有 ack + mark"""
        clear_json_cache()
        msg = self._make_msg("msg-scan1", MsgStatus.PUSHED)
        self._write_inbox("agent_a", [msg])
        # 写 ack.json
        ack_dir = f"{self.data_dir}/inbox/agent_a"
        with open(f"{ack_dir}/ack.json", "w") as f:
            json.dump({"action": "ack", "msg_id": "msg-scan1", "agent": "agent_a", "timestamp": _now_iso()}, f)
        count = scan_ack_files(self.data_dir, {"agent_a": {}})
        assert count == 1, f"预期处理 1 条，得到 {count}"
        # ack.json 应该已被清空
        with open(f"{ack_dir}/ack.json") as f:
            assert json.load(f) == [], "ack.json 应被清空"


if __name__ == "__main__":
    t = TestAckHandler()
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
