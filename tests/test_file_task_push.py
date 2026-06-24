"""file_task_push 与 phantom 扩展测试。"""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from lib.file_task_push import (
    agent_uses_file_task_push,
    build_file_task_push_body,
    ensure_file_task_work_order,
    is_executable_task,
    should_file_task_push,
    verify_file_task_delivery,
)
from lib.phantom_detect import check_phantom_completion, is_phantom_reply_text


class TestFileTaskPush(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "msg-files"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "msg-results"), exist_ok=True)

    def test_cline_uses_file_mode(self):
        self.assertTrue(agent_uses_file_task_push("cline"))
        self.assertTrue(agent_uses_file_task_push("codex"))
        self.assertFalse(agent_uses_file_task_push("hermes"))

    def test_hermes_large_task_file_mode(self):
        msg = {"id": "msg-big", "type": "task", "content": "x" * 900}
        cfg = {"file_task_content_threshold": 800}
        self.assertTrue(should_file_task_push("hermes_profile", cfg, msg, msg["content"]))
        self.assertFalse(should_file_task_push("hermes_profile", cfg, {"type": "notice"}, "x" * 900))

    def test_codex_push_cli(self):
        from lib.agent_adapters import resolve_push_cli
        agent_cfg = {
            "type": "codex",
            "model": "deepseek-chat",
            "push": {"cwd": "/mailbus/store"},
            "docker": {"service": "lingxiao"},
        }
        cmd = resolve_push_cli("lingxiao", agent_cfg, {"models": {}})
        self.assertIn("codex exec", cmd)
        self.assertIn("deepseek-chat", cmd)
        self.assertIn("MSG", cmd)

    def test_work_order_and_verify(self):
        msg = {"id": "msg-test001", "from": "lingzhao", "type": "task", "content": "改 index.html"}
        mid, wo, rf = ensure_file_task_work_order(self.tmp, "lingxiao", msg)
        self.assertTrue(os.path.isfile(wo))
        ok, reason = verify_file_task_delivery(self.tmp, "lingxiao", msg)
        self.assertFalse(ok)
        self.assertEqual(reason, "missing_msg_results")
        with open(rf, "w", encoding="utf-8") as f:
            json.dump({"agent": "lingxiao", "conclusion": "done", "summary": "ok"}, f)
        ok, reason = verify_file_task_delivery(self.tmp, "lingxiao", msg)
        self.assertTrue(ok)

    def test_phantom_reply(self):
        msg = {"id": "msg-p1", "type": "task", "content": "test", "to": "lingxiao"}
        is_ph, reason = check_phantom_completion(
            self.tmp, "lingxiao", msg,
            reply_text="✅ 任务完成回执",
            agent_type="cline",
        )
        self.assertTrue(is_ph)
        self.assertEqual(reason, "phantom_reply_text")

    def test_push_body_has_paths(self):
        body = build_file_task_push_body(
            from_="lingzhao", msg_id="msg-x", msg_type="task",
            wo_path="/store/msg-files/msg-x.md",
            result_path="/store/msg-results/msg-x.json",
        )
        self.assertIn("msg-files", body)
        self.assertIn("禁止", body)

    def test_executable_task(self):
        self.assertTrue(is_executable_task({"type": "task", "content": "x"}))
        self.assertFalse(is_executable_task({"type": "notice", "action": {"execute": False}}))

    def test_role_flow_pursue_to_planner(self):
        from lib.role_flow import get_next_role, get_next_role_type
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "store")
        self.assertEqual(get_next_role("市场拓展官", "pursue"), "方案设计师")
        self.assertEqual(get_next_role_type(4, "pursue", data_dir), 1)


if __name__ == "__main__":
    unittest.main()
