"""cmd_retry 半重置回归（P0，2026-10-11 修复单）。

事故：`mailbus retry` 只拨 status 不动 state，而 scan 筛选/跳过一律
state 优先（get_msg_state/_should_skip），任务型消息（state=done/
processing/rejected）retry 后永远不会被 scan 重新选中——s6 卡死 14min
的根因；全量模式按 status==FAILED 匹配同样漏掉 state=failed/rejected
而 status 仍为 acknowledged/pushed 的任务终态消息（「retry 清不掉
rejected 终态」）。

回归覆盖：
1. 单条 retry 双字段重置（status+state→pending）并清终态残留，
   重置后 get_msg_state()==PENDING（scan 视角可重新选中）；
2. 全量 retry 按 get_msg_state（state 优先）匹配 failed/rejected，
   纯信封消息（无 state 字段）回落 status 仍匹配；
3. done/closed 不被全量 retry 触碰（误重置已完成产线步会触发幽灵
   重跑，2026-10-04 事故教训）。
"""
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.domain.models import MsgStatus, get_msg_state
from lib.infra.utils import resolve_paths


def _msg(mid, state=None, status=None, **extra):
    m = {
        "id": mid,
        "from": "mailbus",
        "to": "agent-r",
        "type": "task",
        "priority": "normal",
        "content": f"do {mid}",
        "pushed_count": 3,
        "last_pushed_at": "2026-10-10T00:00:00",
        "reminded_count": 2,
        "done_at": "2026-10-10T01:00:00",
        "done_note": "max_pushes 3>=3",
    }
    if state is not None:
        m["state"] = state
    if status is not None:
        m["status"] = status
    m.update(extra)
    return m


class _RetryTestBase(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.mkdtemp(prefix="mb-retry-")
        agents = {"agent-r": {"name": "agent-r", "type": "hermes"}}
        with open(os.path.join(self.data_dir, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"data_dir": self.data_dir, "agents": agents}, f)
        inbox_dir = os.path.join(resolve_paths(self.data_dir)["inbox"], "agent-r")
        os.makedirs(inbox_dir, exist_ok=True)
        self.inbox_file = os.path.join(inbox_dir, "inbox.json")

    def _write_inbox(self, messages):
        with open(self.inbox_file, "w", encoding="utf-8") as f:
            json.dump({"agent": "agent-r", "has_unread": True, "messages": messages}, f)

    def _read_messages(self):
        with open(self.inbox_file, "r", encoding="utf-8") as f:
            return json.load(f)["messages"]

    def _run_retry(self, msg_id=None):
        from lib.application.commands.commands import cmd_retry
        return cmd_retry(SimpleNamespace(data_dir=self.data_dir, msg_id=msg_id))


class TestRetrySingle(_RetryTestBase):
    def test_done_message_fully_reset(self):
        """s6 场景：state=done 的任务消息单条 retry 后必须可被 scan 选中。

        注：Message.to_dict 会丢弃 falsy 字段（done_at=None 等），
        残留清除断言一律用 .get()。
        """
        self._write_inbox([_msg("msg-done", state=MsgStatus.DONE, status=MsgStatus.ACKNOWLEDGED)])
        self._run_retry("msg-done")
        m = self._read_messages()[0]
        self.assertEqual(get_msg_state(m), MsgStatus.PENDING)
        self.assertEqual(m["status"], MsgStatus.PENDING)
        self.assertEqual(m["state"], MsgStatus.PENDING)
        self.assertEqual(m["pushed_count"], 0)
        self.assertIsNone(m.get("done_at"))
        self.assertIsNone(m.get("done_note"))

    def test_processing_message_fully_reset(self):
        """卡 processing 的消息 retry 后同样双字段重置。"""
        self._write_inbox([_msg("msg-proc", state=MsgStatus.PROCESSING, status=MsgStatus.PUSHED)])
        self._run_retry("msg-proc")
        m = self._read_messages()[0]
        self.assertEqual(get_msg_state(m), MsgStatus.PENDING)
        self.assertEqual(m["pushed_count"], 0)
        self.assertEqual(m.get("reminded_count", 0), 0)

    def test_unknown_id_is_noop(self):
        self._write_inbox([_msg("msg-x", state=MsgStatus.DONE, status=MsgStatus.ACKNOWLEDGED)])
        self._run_retry("msg-none")
        m = self._read_messages()[0]
        self.assertEqual(get_msg_state(m), MsgStatus.DONE)


class TestRetryAll(_RetryTestBase):
    def test_state_failed_with_status_acknowledged_is_matched(self):
        """任务终态在 state 而非 status——按 status 匹配会漏（原 bug）。"""
        self._write_inbox([
            _msg("m1", state=MsgStatus.FAILED, status=MsgStatus.ACKNOWLEDGED),
            _msg("m2", state=MsgStatus.REJECTED, status=MsgStatus.PUSHED),
        ])
        self._run_retry()
        msgs = {m["id"]: m for m in self._read_messages()}
        for mid in ("m1", "m2"):
            self.assertEqual(get_msg_state(msgs[mid]), MsgStatus.PENDING, mid)
            self.assertEqual(msgs[mid]["pushed_count"], 0, mid)

    def test_envelope_failed_without_state_still_matched(self):
        """纯信封消息（无 state 字段）回落 status==failed，保持向后兼容。"""
        self._write_inbox([_msg("m3", status=MsgStatus.FAILED)])
        self._run_retry()
        m = self._read_messages()[0]
        self.assertEqual(get_msg_state(m), MsgStatus.PENDING)
        self.assertEqual(m["state"], MsgStatus.PENDING)

    def test_done_and_closed_are_untouched(self):
        """done/closed 不被全量 retry 重置——防幽灵重跑（2026-10-04 事故）。"""
        self._write_inbox([
            _msg("m4", state=MsgStatus.DONE, status=MsgStatus.ACKNOWLEDGED),
            _msg("m5", state=MsgStatus.CLOSED, status=MsgStatus.ACKNOWLEDGED),
        ])
        self._run_retry()
        msgs = {m["id"]: m for m in self._read_messages()}
        self.assertEqual(get_msg_state(msgs["m4"]), MsgStatus.DONE)
        self.assertEqual(get_msg_state(msgs["m5"]), MsgStatus.CLOSED)

    def test_pending_message_not_double_counted(self):
        """已在 pending 的消息不重复重置。"""
        self._write_inbox([
            _msg("m6", state=MsgStatus.PENDING, status=MsgStatus.PENDING, pushed_count=0),
        ])
        rc = self._run_retry()
        self.assertEqual(rc, 0)
        m = self._read_messages()[0]
        self.assertEqual(get_msg_state(m), MsgStatus.PENDING)


if __name__ == "__main__":
    unittest.main()
