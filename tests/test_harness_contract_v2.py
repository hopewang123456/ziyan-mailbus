"""Unit tests for harness contract + discovery helpers."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from lib.application.chain_route import ensure_llm_or_prompt, instantiate_chain
from lib.application.lifecycle import list_active_agents, set_role_enabled
from lib.application.harness.contract import build_contract, write_d1_step_result


class TestHarnessContract(unittest.TestCase):
    def test_build_contract_summary(self):
        c = build_contract(
            agent_id="agent-a",
            msg_id="m1",
            task_id="t1",
            step_id="s1",
            data_dir="/tmp/store",
            framework="none",
            domain_skill_ids=["tdd"],
        )
        self.assertEqual(c.schema, "mailbus-harness-contract-v1")
        self.assertIn("agent-a", c.summary_text)
        self.assertTrue(c.delivery_path.endswith("step-s1.json"))

    def test_d1_write(self):
        with tempfile.TemporaryDirectory() as td:
            path = write_d1_step_result(
                td, "t1", "s1", status="done", summary="ok", agent_id="a", contract_id="c1"
            )
            self.assertTrue(os.path.isfile(path))
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "done")
            self.assertEqual(data["schema"], "mailbus-step-result-v1")


class TestLifecycle(unittest.TestCase):
    def test_list_active_filters_disabled(self):
        cfg = {
            "frameworks": {"openclaw": {"enabled": True}},
            "agents": {
                "xiaoqi": {"type": "openclaw", "enabled": True},
                "yige": {"type": "openclaw", "enabled": False},
            },
        }
        active = list_active_agents(cfg)
        self.assertIn("xiaoqi", active)
        self.assertNotIn("yige", active)

    def test_set_role_enabled(self):
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "config.json"
            cfg_path.write_text(
                json.dumps({"agents": {"a1": {"type": "none", "enabled": False}}}),
                encoding="utf-8",
            )
            r = set_role_enabled(td, "a1", True)
            self.assertTrue(r["ok"])
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            self.assertTrue(cfg["agents"]["a1"]["enabled"])


class TestChainRouter(unittest.TestCase):
    def test_instantiate_without_llm_prompts(self):
        cfg = {"mailbus_internal_llm": {}, "mailbus_chains": {"templates": []}}
        # may ok if ollama running; just ensure no crash
        with tempfile.TemporaryDirectory() as td:
            ensure_llm_or_prompt(cfg)
            instantiate_chain(td, {**cfg, "mailbus_chains": {
                "templates": [{"id": "d", "default": True, "steps": [{"action": "x"}]}]
            }}, task_id="t-demo")


if __name__ == "__main__":
    unittest.main()
