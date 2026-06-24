"""tier 派发与 failover 单元测试。"""

import os
import tempfile
import unittest
from unittest.mock import patch

from lib.dispatch.agent_availability import get_offline_agents
from lib.dispatch.collab_plan import expand_planned_chain_for_collab
from lib.dispatch.role_resolver import resolve_agent_for_role_type
from lib.dispatch.tier_filter import filter_candidates_by_tier
from lib.utils import json_write


class TierFilterTests(unittest.TestCase):
    def test_pro_prefers_lingyun(self):
        with patch.dict(os.environ, {"MAILBUS_ALLOW_PRO": "1"}):
            out = filter_candidates_by_tier(
                8, ["lingxiao", "dali", "lingyun"],
                {"model_tier": "pro"},
                {"lingxiao": {"models": ["deepseek-flash"]}},
            )
        self.assertIn("lingyun", out)
        self.assertNotIn("dali", out)

    def test_flash_prefers_dali_lingxiao(self):
        out = filter_candidates_by_tier(
            8, ["lingxiao", "dali", "lingyun"],
            {"model_tier": "flash"},
            {},
        )
        self.assertIn("dali", out)
        self.assertIn("lingxiao", out)
        self.assertNotIn("lingyun", out)

    def test_empty_pool_fallback(self):
        out = filter_candidates_by_tier(8, ["lingyun"], {"model_tier": "flash"}, {})
        self.assertEqual(out, ["lingyun"])


class CollabPlanTests(unittest.TestCase):
    def test_dual_coding_expands(self):
        env = {"constraints": {"dispatch": {"dual_coding": True}}}
        chain = [{"role_type": 8, "reason": "dev"}]
        out = expand_planned_chain_for_collab(chain, env)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["pin_agent"], "lingyun")
        self.assertEqual(out[1]["pin_agent"], "dali")
        self.assertEqual(out[1]["parallel_with"], "dual")


class OfflineAgentsTests(unittest.TestCase):
    def test_offline_detection(self):
        with tempfile.TemporaryDirectory() as td:
            json_write(os.path.join(td, "heartbeat.json"), {
                "agents": {
                    "lingyun": {"status": "offline", "missed_pings": 5},
                    "dali": {"status": "online", "missed_pings": 0},
                }
            })
            offline = get_offline_agents(td)
            self.assertIn("lingyun", offline)
            self.assertNotIn("dali", offline)


class ResolveAgentTests(unittest.TestCase):
    def test_offline_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            roles_dir = os.path.join(td, "roles", "json")
            os.makedirs(roles_dir, exist_ok=True)
            json_write(os.path.join(roles_dir, "role-types.json"), {
                "roles": {
                    "8": {"candidates": ["lingyun", "dali", "lingxiao"]}
                }
            })
            json_write(os.path.join(td, "config.json"), {"agents": {}})
            json_write(os.path.join(td, "heartbeat.json"), {
                "agents": {"lingyun": {"status": "offline", "missed_pings": 5}}
            })
            agent, meta = resolve_agent_for_role_type(
                td, 8, action={"model_tier": "pro"},
                forbidden={"lingyun"},
            )
            self.assertNotEqual(agent, "lingyun")
            self.assertIn("lingyun", meta.get("forbidden", []))


if __name__ == "__main__":
    unittest.main()
