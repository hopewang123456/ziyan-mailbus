"""v2/v3 已知 bug 回归 — 对应 conversation 中修复项。"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.adapters.config.agent_config import validate_agents
from lib.domain.models import Inbox, MsgStatus
from lib.application.orchestration.pipeline.routing import resolve_next_assignee
from lib.application.orchestration.pipeline.task import (
    should_auto_ack_message,
    should_create_tracker_for_send,
    verify_pipeline_step_delivery,
    pipeline_repush_cooldown_minutes,
    is_current_pipeline_assignee,
    pipeline_inbox_message_stale,
)
from lib.application.orchestration.pipeline.trigger import _close_pipeline_inbox
from lib.application.scan import _cleanup_stale_queue_files, recover_inbox_stale_states
from lib.application.ops.self_heal import sync_tracker_and_inbox, normalize_legacy_tracker_audit_flags
from lib.application.orchestration.tracker import TaskTracker, TaskStatus
from lib.infra.utils import json_write, resolve_paths


def _write_task(tmp, task_id, chain, status="running", summary=""):
    path = os.path.join(tmp, "tasks", f"{task_id}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json_write(path, {
        "task_id": task_id,
        "summary": summary or f"【{task_id}】test",
        "assignee": chain[-1].get("to_person", "agent-a"),
        "status": status,
        "chain": chain,
    })


class TestV2BugRegression(unittest.TestCase):
    """覆盖 v2 夜间修复 + v3 诊断暴露的问题。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for sub in (
            "tasks", "msg-results", "inbox/agent-a", "inbox/agent-d",
            "queue/urgent", "queue/normal", "iterations",
        ):
            os.makedirs(os.path.join(self.tmp, sub), exist_ok=True)
        json_write(
            os.path.join(self.tmp, "config.json"),
            {"pipeline_ops": {"primary_repush_cooldown_minutes": 15, "repush_cooldown_minutes": 8}},
        )
        json_write(
            os.path.join(self.tmp, "iterations", "iteration-state.json"),
            {"primary_task_id": "game-stellar-test"},
        )

    # --- P0: pipeline auto_ack 僵尸 ---
    def test_pipeline_task_not_auto_ack(self):
        chain = [{"step": 1, "to_person": "agent-a", "status": "running", "planned_agents": ["agent-d"]}]
        _write_task(self.tmp, "game-stellar-test", chain)
        msg = {"to": "agent-a", "content": "【game-stellar-test】Step1", "type": "task", "action": {"execute": True}}
        self.assertFalse(should_auto_ack_message(msg, self.tmp, "hermes_profile"))

    # --- P0: notice 不应占 processing 槽（scanner 逻辑在 recover 里 digest notice）---
    def test_notice_not_treated_as_pipeline_execute(self):
        msg = {"to": "agent-a", "content": "团队规范已更新", "type": "notice"}
        self.assertTrue(should_auto_ack_message(msg, self.tmp, "hermes_profile"))

    # --- P0: bus send 不建重复 tracker ---
    def test_no_duplicate_tracker_for_pipeline_task_id(self):
        chain = [{"step": 1, "to_person": "agent-a", "status": "running", "planned_agents": ["agent-d"]}]
        _write_task(self.tmp, "game-stellar-test", chain)
        self.assertFalse(should_create_tracker_for_send("【game-stellar-test】Step1", self.tmp))

    def test_cancel_duplicate_msg_tracker_on_heal(self):
        chain = [{"step": 1, "to_person": "agent-a", "status": "running", "planned_agents": ["agent-d"]}]
        _write_task(self.tmp, "game-stellar-test", chain)
        tr = TaskTracker(self.tmp)
        tr.create(task_id="msg-fake-001", summary="【game-stellar-test】dup", assignee="agent-a")
        n = normalize_legacy_tracker_audit_flags(self.tmp)
        self.assertGreaterEqual(n, 1)
        self.assertEqual(tr.get("msg-fake-001")["status"], "cancelled")

    # --- P0: planned pop 跳过连续同 agent (agent-m→agent-m) ---
    def test_planned_skips_consecutive_same_agent(self):
        chain = [{
            "step": 5,
            "to_person": "agent-m",
            "to_role": "调度员",
            "status": "running",
            "planned_agents": ["agent-m", "agent-g"],
        }]
        role, person = resolve_next_assignee(chain, {}, "调度员", "done", agents={})
        self.assertEqual(person, "agent-g")
        self.assertEqual(chain[0]["planned_agents"], [])

    # --- P0: phantom completion — 无 msg-results 验收失败 ---
    def test_verify_delivery_rejects_missing_msg_results(self):
        chain = [{"step": 1, "to_person": "agent-a", "status": "running"}]
        _write_task(self.tmp, "game-stellar-test", chain)
        ok, reason = verify_pipeline_step_delivery(
            self.tmp, "agent-a",
            {"content": "【game-stellar-test】", "task_id": "game-stellar-test"},
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "missing_msg_results")

    def test_verify_delivery_accepts_valid_msg_results(self):
        chain = [{"step": 1, "to_person": "agent-a", "status": "running", "step_id": "s1"}]
        _write_task(self.tmp, "game-stellar-test", chain)
        step_dir = os.path.join(self.tmp, "msg-results", "game-stellar-test")
        os.makedirs(step_dir, exist_ok=True)
        json_write(os.path.join(step_dir, "step-s1.json"), {
            "task_id": "game-stellar-test",
            "agent": "agent-a",
            "pipeline_step": 1,
            "step_id": "s1",
            "conclusion": "done",
            "summary": "ok",
        })
        ok, reason = verify_pipeline_step_delivery(
            self.tmp, "agent-a",
            {"content": "【game-stellar-test】", "task_id": "game-stellar-test"},
        )
        self.assertTrue(ok, reason)
        self.assertEqual(reason, "ok")

    def test_verify_delivery_stale_prior_step_results(self):
        """Step5 assignee 不应因 Step4 遗留 msg-results 被判 wrong_agent。"""
        chain = [{"step": 5, "to_person": "agent-g", "status": "running"}]
        _write_task(self.tmp, "game-stellar-test", chain)
        json_write(os.path.join(self.tmp, "msg-results", "game-stellar-test.json"), {
            "task_id": "game-stellar-test",
            "agent": "agent-m",
            "pipeline_step": 4,
            "conclusion": "done",
            "summary": "step4 done",
        })
        ok, reason = verify_pipeline_step_delivery(
            self.tmp, "agent-g",
            {"content": "【game-stellar-test】", "task_id": "game-stellar-test"},
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "missing_msg_results")

    # --- P0: success 后关闭 pipeline inbox ---
    def test_close_pipeline_inbox_on_success(self):
        agents = {"agent-a": {}}
        paths = resolve_paths(self.tmp)
        tid = "game-stellar-test"
        inbox_file = os.path.join(self.tmp, "inbox", "agent-a", "inbox.json")
        json_write(inbox_file, {
            "agent": "agent-a",
            "has_unread": True,
            "messages": [{
                "id": "msg-test-1",
                "content": f"【{tid}】Step1",
                "type": "task",
                "state": "processing",
                "status": "processing",
            }],
        })
        n = _close_pipeline_inbox(self.tmp, paths, tid, agents)
        self.assertEqual(n, 1)
        inbox = Inbox.from_dict(json.load(open(inbox_file)))
        self.assertEqual(inbox.msg_field(inbox.messages[0], "state", ""), MsgStatus.DONE)

    # --- P1: inbox 不因 msg-results 过早 done（running step 未 consumed）---
    def test_inbox_not_closed_while_step_running(self):
        tid = "game-stellar-test"
        chain = [{"step": 1, "to_person": "agent-a", "status": "running", "result_consumed": False}]
        _write_task(self.tmp, tid, chain)
        json_write(os.path.join(self.tmp, "msg-results", f"{tid}.json"), {
            "task_id": tid, "agent": "agent-a", "pipeline_step": 1, "conclusion": "done",
        })
        inbox_file = os.path.join(self.tmp, "inbox", "agent-a", "inbox.json")
        json_write(inbox_file, {
            "agent": "agent-a",
            "has_unread": True,
            "messages": [{
                "id": "msg-x",
                "content": f"【{tid}】task",
                "type": "task",
                "state": "processing",
            }],
        })
        stats = sync_tracker_and_inbox(self.tmp, {"agent-a": {}})
        self.assertEqual(stats.get("inbox_closed", 0), 0)
        inbox = Inbox.from_dict(json.load(open(inbox_file)))
        self.assertNotEqual(inbox.msg_field(inbox.messages[0], "state", ""), MsgStatus.DONE)

    # --- P1: stale queue 清理 ---
    def test_stale_queue_removed_when_inbox_empty(self):
        json_write(os.path.join(self.tmp, "inbox", "agent-a", "inbox.json"), {
            "agent": "agent-a", "has_unread": False, "messages": [],
        })
        json_write(os.path.join(self.tmp, "queue", "urgent", "agent-a.json"), [{"id": "stale"}])
        n = _cleanup_stale_queue_files(self.tmp, {"agent-a": {}})
        self.assertEqual(n, 1)

    # --- P1: primary pipeline repush cooldown ---
    def test_primary_repush_cooldown_config(self):
        cfg = json.load(open(os.path.join(self.tmp, "config.json")))
        cd = pipeline_repush_cooldown_minutes(cfg, is_primary=True)
        self.assertGreaterEqual(cd, 15)

    # --- L2: 已完成步骤的 agent 不再收 pipeline 重推 ---
    def test_stale_pipeline_inbox_after_step_advance(self):
        tid = "pipeline-mini-test"
        chain = [
            {"step": 1, "to_person": "agent-a", "status": "completed", "result_consumed": True},
            {"step": 2, "to_person": "agent-d", "status": "running", "result_consumed": False},
        ]
        _write_task(self.tmp, tid, chain)
        self.assertTrue(pipeline_inbox_message_stale(self.tmp, "agent-a", f"【{tid}】Step1"))
        self.assertFalse(pipeline_inbox_message_stale(self.tmp, "agent-d", f"【{tid}】Step2"))
        inbox_file = os.path.join(self.tmp, "inbox", "agent-a", "inbox.json")
        json_write(inbox_file, {
            "agent": "agent-a",
            "has_unread": True,
            "messages": [{
                "id": "msg-lz-stale",
                "content": f"【{tid}】Step1",
                "type": "task",
                "state": "pending",
                "action": {"execute": True},
            }],
        })
        stats = recover_inbox_stale_states(self.tmp, {"agent-a": {}, "agent-d": {}})
        self.assertGreaterEqual(stats.get("agent-a", 0), 1)
        inbox = Inbox.from_dict(json.load(open(inbox_file)))
        self.assertEqual(inbox.msg_field(inbox.messages[0], "state", ""), MsgStatus.DONE)

    # --- L2: 当前 assignee 的 resending → pending ---
    def test_resending_reset_for_current_assignee(self):
        tid = "pipeline-mini-test"
        chain = [{"step": 2, "to_person": "agent-d", "status": "running", "result_consumed": False}]
        _write_task(self.tmp, tid, chain)
        self.assertTrue(is_current_pipeline_assignee(self.tmp, tid, "agent-d"))
        inbox_file = os.path.join(self.tmp, "inbox", "agent-d", "inbox.json")
        json_write(inbox_file, {
            "agent": "agent-d",
            "has_unread": True,
            "messages": [{
                "id": "msg-lx-resend",
                "content": f"【{tid}】Step2",
                "type": "task",
                "state": "closed",
                "status": "resending",
                "action": {"execute": True},
            }],
        })
        stats = recover_inbox_stale_states(self.tmp, {"agent-d": {}})
        self.assertGreaterEqual(stats.get("agent-d", 0), 1)
        inbox = Inbox.from_dict(json.load(open(inbox_file)))
        self.assertEqual(inbox.msg_field(inbox.messages[0], "state", ""), MsgStatus.PENDING)

    # --- token burn: Round2 done 不应被 orchestrator 重置为 pending ---
    def test_round2_done_not_reset_by_orchestrator(self):
        from lib.application.orchestration.execution import reconcile_execution_order

        json_write(os.path.join(self.tmp, "iterations", "iteration-state.json"), {
            "primary_task_id": "game-stellar-v3-20260617",
        })
        json_write(os.path.join(self.tmp, "iterations", "round-1-gate.json"), {
            "round2_unlocked": False,
        })
        inbox_file = os.path.join(self.tmp, "inbox", "agent-a", "inbox.json")
        json_write(inbox_file, {
            "agent": "agent-a",
            "has_unread": False,
            "messages": [{
                "id": "msg-r2-done",
                "content": "【msg-round2-001】Round2 backlog task",
                "type": "task",
                "state": MsgStatus.DONE,
                "action": {"execute": True},
            }],
        })
        stats = reconcile_execution_order(self.tmp, {"agent-a": {}}, mode="light")
        self.assertEqual(stats.get("reset_inbox", 0), 0)
        inbox = Inbox.from_dict(json.load(open(inbox_file)))
        self.assertEqual(inbox.msg_field(inbox.messages[0], "state", ""), MsgStatus.DONE)

    def test_push_cooldown_skips_recent_push(self):
        from lib.application.scan import should_skip_push
        from datetime import datetime, timezone, timedelta

        ts = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S%z")
        msg = {
            "id": "msg-cooldown",
            "content": "test",
            "pushed_count": 1,
            "last_pushed_at": ts,
        }
        cfg = {"push_cooldown_minutes": 10}
        skip, reason = should_skip_push(self.tmp, msg, cfg)
        self.assertTrue(skip)
        self.assertIn("cooldown", reason)


class TestAgentConfigValidation(unittest.TestCase):
    def test_store_config_agents_valid(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        store_cfg = os.path.join(root, "store", "config.json")
        if not os.path.isfile(store_cfg):
            self.skipTest("store/config.json not in repo")
        full = json.load(open(store_cfg, encoding="utf-8"))
        agents = full.get("agents", {})
        agent_types = full.get("agent_types", {})
        errors = validate_agents(agents, agent_types)
        self.assertEqual(errors, [], msg="\n".join(errors))


if __name__ == "__main__":
    unittest.main()
