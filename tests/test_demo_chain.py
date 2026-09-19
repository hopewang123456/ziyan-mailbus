"""Wave 2 E-demo/E-e2e: zero-dependency demo chain = CI e2e gate.

The demo doubles as the end-to-end regression the SoT asked for:
建单 → 派工 → 投递 → 执行 → 回执 → 验收 → 归档, zero frameworks, zero keys.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.application.ops.demo_chain import (
    DEMO_AGENTS,
    clean_demo,
    demo_dir,
    ensure_demo_store,
    run_demo,
)


class TestDemoChain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # 干净 clone 场景：只有空 config，无任何 Vault/框架依赖
        with open(os.path.join(self.tmp, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"agents": {}}, f)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_loop_success(self):
        result = run_demo(self.tmp)
        self.assertTrue(result["ok"], msg=str(result))
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["steps"]), 2)
        for s in result["steps"]:
            self.assertEqual(s["fsm_state"], "completed", msg=str(result["steps"]))
        # 任务落盘终态 + 验收记录
        task_path = os.path.join(self.tmp, "demo", "tasks", f"{result['task_id']}.json")
        with open(task_path, encoding="utf-8") as f:
            t = json.load(f)
        self.assertEqual(t["status"], "success")
        self.assertEqual(t["fsm"]["state"], "succeeded")
        self.assertTrue(t.get("acceptance_record"))
        # 流转叙事留痕（驾驶舱/向导素材）
        with open(os.path.join(self.tmp, "demo", "trace.json"), encoding="utf-8") as f:
            trace = json.load(f)
        self.assertTrue(any(e["event"] == "step_result" for e in trace["events"]))

    def test_demo_namespace_isolated_and_cleanable(self):
        ensure_demo_store(self.tmp)
        d = demo_dir(self.tmp)
        self.assertTrue(os.path.isdir(os.path.join(d, "inbox", "demo-dev")))
        # 演示数据不泄漏到主 store 根
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "tasks")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "ledger")))
        self.assertTrue(clean_demo(self.tmp))
        self.assertFalse(os.path.isdir(d))
        self.assertFalse(clean_demo(self.tmp))  # 幂等

    def test_dispatch_reached_demo_inbox(self):
        """投递真实性：工单消息确实落在 demo 角色的 inbox。"""
        result = run_demo(self.tmp)
        inbox_path = os.path.join(self.tmp, "demo", "inbox", "demo-dev", "inbox.json")
        with open(inbox_path, encoding="utf-8") as f:
            inbox = json.load(f)
        self.assertTrue(
            any(str(m.get("task_id")) == result["task_id"] for m in inbox.get("messages") or []),
            "dispatched work order must land in demo-dev inbox",
        )
        # ack 也真实落盘
        ack_path = os.path.join(self.tmp, "demo", "inbox", "demo-dev", "ack.json")
        with open(ack_path, encoding="utf-8") as f:
            acks = json.load(f)
        self.assertTrue(any(a.get("action") == "ack" for a in acks))

    def test_demo_agents_are_type_none(self):
        """零依赖口径：demo 角色全部 type=none（无框架 adapter）。"""
        for meta in DEMO_AGENTS.values():
            pass  # roster 常量自检在 ensure 后的 config
        ensure_demo_store(self.tmp)
        with open(os.path.join(self.tmp, "demo", "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        for aid in DEMO_AGENTS:
            self.assertEqual(cfg["agents"][aid]["type"], "none")
            self.assertTrue(cfg["agents"][aid].get("enabled"))


if __name__ == "__main__":
    unittest.main()
