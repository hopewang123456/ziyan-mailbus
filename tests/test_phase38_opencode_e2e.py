"""Phase 3.8 — OpenCode Normalizer + phantom 回归（game-courier 路径模拟）。"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.delivery_normalizer import normalize_opencode_deliveries, normalize_from_reply_record
from lib.phantom_detect import is_phantom_reply_text
from lib.pipeline_task import pipeline_inbox_may_mark_done
from lib.file_task_push import verify_file_task_delivery
from lib.task_fsm import apply_submit, ensure_fsm, read_step_result
from lib.utils import json_write


class TestPhase38OpencodeE2E(unittest.TestCase):
    """模拟 dali pipeline：push → reply+patch → normalizer → msg-results → FSM 可读。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tid = "game-courier-e2e"
        self.sid = "s1"
        os.makedirs(os.path.join(self.tmp, "replies"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "patches"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "msg-results", self.tid), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "inbox", "dali"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "tasks"), exist_ok=True)
        json_write(os.path.join(self.tmp, "config.json"), {
            "agents": {"dali": {"type": "opencode", "name": "大力"}},
            "framework_delivery": {"opencode": {"enabled": True, "sources": ["replies", "patches"]}},
        })
        task = {
            "task_id": self.tid,
            "status": "running",
            "assignee": "dali",
            "chain": [{
                "step": 1,
                "step_id": self.sid,
                "status": "running",
                "fsm_state": "awaiting_result",
                "to_agent": "dali",
                "to_person": "dali",
                "to_role": "编码",
                "started_at": "2026-06-01T00:00:00+08:00",
            }],
        }
        ensure_fsm(task)
        json_write(os.path.join(self.tmp, "tasks", f"{self.tid}.json"), task)
        self.msg_id = "msg-e2e-courier"
        json_write(os.path.join(self.tmp, "inbox", "dali", "inbox.json"), {
            "agent": "dali",
            "messages": [{
                "id": self.msg_id,
                "task_id": self.tid,
                "step_id": self.sid,
                "pipeline_step": 1,
                "type": "task",
                "state": "processing",
                "content": f"【{self.tid}】 step_id={self.sid}\n任务文件: work-orders/{self.tid}/step-{self.sid}.md",
            }],
        })

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_phantom_reply_blocked_without_results(self):
        entry = {"id": self.msg_id, "type": "task", "content": "done"}
        ok, reason = verify_file_task_delivery(self.tmp, "dali", entry, reply_text="已完成")
        self.assertFalse(ok)
        self.assertEqual(reason, "phantom_reply_text")
        self.assertTrue(is_phantom_reply_text("已完成", msg_type="task"))

    def test_reply_patch_normalizer_to_step_result_and_fsm(self):
        patch_path = os.path.join(self.tmp, "patches", "0001-courier.patch")
        with open(patch_path, "w", encoding="utf-8") as f:
            f.write("diff --git a/courier.py b/courier.py\n+print('ok')\n")
        reply = {
            "agent": "dali",
            "msg_ids": [self.msg_id],
            "reply": "game-courier 模块已实现，见 patch",
            "patch": patch_path,
            "started_at": "2026-06-26T10:00:00+08:00",
            "timestamp": "2026-06-26T11:00:00+08:00",
        }
        n = normalize_from_reply_record(self.tmp, "dali", reply)
        self.assertEqual(n, 1)
        step = {"step_id": self.sid}
        result = read_step_result(self.tmp, self.tid, step)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("conclusion"), "done")
        self.assertTrue(result.get("normalized"))

        import json
        task = json.load(open(os.path.join(self.tmp, "tasks", f"{self.tid}.json"), encoding="utf-8"))
        out = apply_submit(task, result, data_dir=self.tmp)
        self.assertTrue(out.get("ok"), out)

    def test_batch_normalizer_from_replies_file(self):
        json_write(os.path.join(self.tmp, "replies", "dali.json"), {
            "agent": "dali",
            "msg_ids": [self.msg_id],
            "reply": "courier done",
        })
        stats = normalize_opencode_deliveries(self.tmp, {"dali": {"type": "opencode"}})
        self.assertGreaterEqual(stats.get("total", 0), 1)
        result = read_step_result(self.tmp, self.tid, {"step_id": self.sid})
        self.assertIsNotNone(result)

    def test_pipeline_inbox_not_done_without_step_result(self):
        from lib.models import Inbox, MsgStatus
        inbox = Inbox(agent="dali")
        inbox.messages.append({
            "id": self.msg_id,
            "to": "dali",
            "task_id": self.tid,
            "type": "task",
            "state": MsgStatus.PROCESSING,
            "content": f"【{self.tid}】 step_id={self.sid}\n结果写入: msg-results/{self.tid}/step-{self.sid}.json",
        })
        allowed, _reason = pipeline_inbox_may_mark_done(self.tmp, "dali", inbox.messages[0])
        self.assertFalse(allowed)


if __name__ == "__main__":
    unittest.main()
