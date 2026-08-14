"""Pipeline 工种 failover 与催办保护。"""
from __future__ import annotations

import os
import tempfile
import unittest

from lib.application.orchestration.dispatch.pipeline_step_failover import (
    failover_pipeline_step,
    next_failover_agent_for_step,
    role_failover_plan,
)
from lib.application.orchestration.dispatch.role_resolver import role_type_candidates
from lib.application.orchestration.pipeline.task import (
    is_current_pipeline_assignee,
    pipeline_message_protected_from_auto_close,
)
from lib.application.orchestration.tracker import TaskTracker
from lib.infra.utils import json_write


def _write_role_types(tmp: str) -> None:
    os.makedirs(os.path.join(tmp, "roles", "json"), exist_ok=True)
    json_write(os.path.join(tmp, "roles", "json", "role-types.json"), {
        "roles": {
            "1": {"key": "planner", "display": {"zh": "方案设计师"}, "candidates": ["agent-a"]},
            "5": {"key": "reviewer", "display": {"zh": "审查官"}, "candidates": ["agent-e"]},
            "8": {"key": "developer", "display": {"zh": "开发工程师"}, "candidates": ["agent-g", "agent-i"]},
        },
    })


class PipelineStepFailoverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "tasks"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "inbox", "agent-e"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "inbox", "agent-g"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "inbox", "agent-i"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "inbox", "agent-a"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "dispatch"), exist_ok=True)
        _write_role_types(self.tmp)
        json_write(os.path.join(self.tmp, "config.json"), {
            "agents": {
                "agent-e": {"type": "codex"},
                "agent-g": {"type": "codex"},
                "agent-i": {"type": "opencode"},
                "agent-a": {"type": "hermes"},
            },
            "pipeline_ops": {
                "role_failover": {
                    "5": {"similar_role_types": [8, 1]},
                },
            },
        })
        tid = "game-courier-test"
        task = {
            "task_id": tid,
            "status": "running",
            "assignee": "agent-e",
            "chain": [{
                "step": 8,
                "step_id": "s8",
                "status": "running",
                "role_type": 5,
                "to_agent": "agent-e",
                "to_person": "agent-e",
                "to_role": "审查官",
                "from_agent": "agent-a",
            }],
        }
        json_write(os.path.join(self.tmp, "tasks", f"{tid}.json"), task)

    def test_assignee_check_argument_order(self):
        tid = "game-courier-test"
        self.assertTrue(is_current_pipeline_assignee(self.tmp, tid, "agent-e"))
        self.assertFalse(is_current_pipeline_assignee(self.tmp, tid, "agent-g"))

    def test_pipeline_protected_from_auto_close(self):
        tid = "game-courier-test"
        m = {
            "type": "task",
            "to": "agent-e",
            "content": f"📋 【{tid}】pipeline 步骤",
        }
        self.assertTrue(
            pipeline_message_protected_from_auto_close(self.tmp, "agent-e", m),
        )

    def test_role_failover_plan_reviewer(self):
        plan = role_failover_plan(5, json_read_config := __import__("lib.infra.utils", fromlist=["json_read"]).json_read(
            os.path.join(self.tmp, "config.json"), {}))
        self.assertEqual(plan, [5, 8, 1])

    def test_role_failover_agents_for_reviewer(self):
        cfg = __import__("lib.infra.utils", fromlist=["json_read"]).json_read(
            os.path.join(self.tmp, "config.json"), {})
        plan = role_failover_plan(5, cfg)
        chain: list[str] = []
        for rt in plan:
            for agent in role_type_candidates(rt, self.tmp):
                if agent not in chain:
                    chain.append(agent)
        self.assertEqual(chain, ["agent-e", "agent-g", "agent-i", "agent-a"])
        self.assertNotIn("agent-h", chain)

    def test_next_failover_picks_developer_not_agent_h(self):
        task = TaskTracker(self.tmp).get("game-courier-test")
        picked = next_failover_agent_for_step(self.tmp, task)
        self.assertIsNotNone(picked)
        agent, meta = picked
        self.assertIn(agent, ("agent-g", "agent-i"))
        self.assertEqual(meta.get("failover_tier"), "similar_role")
        self.assertEqual(meta.get("failover_to_role_type"), 8)

    def test_failover_updates_task_role_meta(self):
        new_agent = failover_pipeline_step(
            self.tmp, "game-courier-test", reason="test", from_agent="agent-e",
        )
        self.assertIn(new_agent, ("agent-g", "agent-i"))
        task = TaskTracker(self.tmp).get("game-courier-test")
        step = task["chain"][0]
        self.assertEqual(step["to_agent"], new_agent)
        self.assertIn("agent-e", step.get("failover_tried", []))
        self.assertEqual(step.get("dispatch_meta", {}).get("failover_to_role_type"), 8)


if __name__ == "__main__":
    unittest.main()
