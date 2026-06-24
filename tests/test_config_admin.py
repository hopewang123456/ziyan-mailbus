"""配置中心 API 单元测试。"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.config_admin import env_status, get_section, patch_env, patch_section
from lib.utils import json_write


def _seed(tmp: str) -> None:
    root = os.path.join(os.path.dirname(__file__), "..", "store")
    shutil.copytree(
        os.path.join(root, "roles"),
        os.path.join(tmp, "roles"),
        dirs_exist_ok=True,
    )
    shutil.copytree(
        os.path.join(root, "workflows"),
        os.path.join(tmp, "workflows"),
        dirs_exist_ok=True,
    )
    cfg_path = os.path.join(root, "config.json")
    import json
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    json_write(os.path.join(tmp, "config.json"), cfg)


class TestConfigAdmin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _seed(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_get_llm_section(self):
        out = get_section(self.tmp, "mailbus_internal_llm")
        self.assertEqual(out["section"], "mailbus_internal_llm")
        self.assertIn("enabled", out["data"])

    def test_get_agents_section(self):
        out = get_section(self.tmp, "agents")
        self.assertTrue(out["agents"])
        self.assertIn("runtime_notes", out)

    def test_patch_workflow(self):
        result, _ = patch_section(
            self.tmp,
            "mailbus_workflow",
            {"tool_live_gates": ["publish_go", "test_gate"]},
        )
        self.assertEqual(result["section"], "mailbus_workflow")
        out = get_section(self.tmp, "mailbus_workflow")
        self.assertIn("test_gate", out["data"]["tool_live_gates"])

    def test_patch_agent_models(self):
        patch_section(
            self.tmp,
            "agents",
            {"agent_id": "dali", "fields": {"models": ["deepseek-flash"], "max_concurrency": 2}},
        )
        out = get_section(self.tmp, "agents")
        dali = next(a for a in out["agents"] if a["id"] == "dali")
        self.assertEqual(dali["models"], ["deepseek-flash"])
        self.assertEqual(dali["max_concurrency"], 2)

    def test_env_status_shape(self):
        st = env_status(self.tmp)
        self.assertIn("groups", st)
        self.assertIn("llm", st["groups"])

    def test_get_scheduler_section(self):
        out = get_section(self.tmp, "scheduler")
        self.assertEqual(out["section"], "scheduler")
        self.assertIn("enabled", out["data"])
        self.assertIsInstance(out["data"].get("jobs"), list)

    def test_get_intake_section(self):
        out = get_section(self.tmp, "mailbus_intake_bridge")
        self.assertEqual(out["section"], "mailbus_intake_bridge")
        self.assertIsInstance(out["data"], dict)

    def test_get_codex_section(self):
        out = get_section(self.tmp, "mailbus_codex")
        self.assertEqual(out["section"], "mailbus_codex")
        self.assertIsInstance(out["data"], dict)

    def test_get_claude_section(self):
        out = get_section(self.tmp, "mailbus_claude")
        self.assertEqual(out["section"], "mailbus_claude")
        self.assertIsInstance(out["data"], dict)

    def test_patch_claude_enabled(self):
        patch_section(
            self.tmp,
            "mailbus_claude",
            {
                "platform": "windows",
                "windows": {"enabled": True, "claude_bin": "claude"},
                "linux": {"enabled": False},
            },
        )
        out = get_section(self.tmp, "mailbus_claude")
        self.assertEqual(out["data"]["platform"], "windows")
        self.assertTrue(out["data"]["windows"]["enabled"])
        self.assertFalse(out["data"]["linux"]["enabled"])

    def test_patch_codex_sync_flags(self):
        patch_section(
            self.tmp,
            "mailbus_codex",
            {"windows": {"sync_on_launch": False, "ensure_gateway_container": False}},
        )
        out = get_section(self.tmp, "mailbus_codex")
        self.assertFalse(out["data"]["windows"]["sync_on_launch"])
        self.assertFalse(out["data"]["windows"]["ensure_gateway_container"])

    def test_patch_claude_browser_ports(self):
        patch_section(
            self.tmp,
            "mailbus_claude",
            {"windows": {"browser_ports": {"lingyun": 9260, "lingyan": 9261}}},
        )
        out = get_section(self.tmp, "mailbus_claude")
        self.assertEqual(out["data"]["windows"]["browser_ports"]["lingyan"], 9261)


if __name__ == "__main__":
    unittest.main()
