"""配置中心 API 单元测试。"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.adapters.config.config_admin import env_status, get_section, patch_env, patch_section
from lib.infra.utils import json_write


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
        seed = get_section(self.tmp, "agents")
        agents = seed.get("agents") or []
        if not agents:
            self.skipTest("no seeded agents")
        aid = agents[0]["id"]
        patch_section(
            self.tmp,
            "agents",
            {"agent_id": aid, "fields": {"models": ["deepseek-flash"], "max_concurrency": 2}},
        )
        out = get_section(self.tmp, "agents")
        found = next(a for a in out["agents"] if a["id"] == aid)
        self.assertEqual(found["models"], ["deepseek-flash"])
        self.assertEqual(found["max_concurrency"], 2)

    def test_env_status_shape(self):
        st = env_status(self.tmp)
        self.assertIn("groups", st)
        self.assertIn("llm", st["groups"])

    def test_env_status_has_vault_and_memory_specs(self):
        st = env_status(self.tmp)
        keys = {s["key"] for s in st.get("specs", [])}
        self.assertIn("AGENT_VAULT_ROOT", keys)
        self.assertIn("MEMORY_BRIDGE_AGENTMEMORY", keys)
        self.assertIn("MAILBUS_SKILLS_ROOT", keys)

    def test_agents_section_has_install_fields(self):
        out = get_section(self.tmp, "agents")
        for it in out.get("agents") or []:
            self.assertIn("install_path", it)
            self.assertIn("install_path_default", it)
            self.assertIn("run_target", it)
            self.assertIn("run_targets", it)
            self.assertIn("install_configured", it)

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
            {"windows": {"browser_ports": {"agent-h": 9260, "agent-f": 9261}}},
        )
        out = get_section(self.tmp, "mailbus_claude")
        self.assertEqual(out["data"]["windows"]["browser_ports"]["agent-f"], 9261)

    def test_get_smart_routing_section(self):
        out = get_section(self.tmp, "smart_routing")
        self.assertEqual(out["section"], "smart_routing")
        self.assertIn("enabled", out["data"])
        self.assertIn("ollama", out)
        self.assertIn("L0", out["tier_options"])

    def test_patch_smart_routing(self):
        patch_section(
            self.tmp,
            "smart_routing",
            {
                "enabled": True,
                "use_ollama": True,
                "tier_map": {"L1": "ollama-local", "L3": "deepseek-flash"},
            },
        )
        out = get_section(self.tmp, "smart_routing")
        self.assertEqual(out["data"]["tier_map"]["L1"], "ollama-local")
        self.assertTrue(out["data"]["use_ollama"])

    def test_get_asset_paths_section(self):
        out = get_section(self.tmp, "asset_paths")
        self.assertEqual(out["section"], "asset_paths")
        items = out["data"]["items"]
        self.assertEqual(len(items), 3)
        keys = {it["key"] for it in items}
        self.assertEqual(keys, {"skills", "rules", "identity"})
        for it in items:
            self.assertIn("mode", it)
            self.assertIn("env", it)
            self.assertIn("default", it)
            self.assertIn("vault", it)

    def test_patch_asset_paths_custom_and_default(self):
        # 模拟 store 在 mail 根下：data_dir = {base}/store → .env 在 {base}/.env
        base = tempfile.mkdtemp()
        try:
            data_dir = os.path.join(base, "store")
            os.makedirs(data_dir)
            import json as _json
            _json.dump(
                _json.load(open(os.path.join(os.path.dirname(__file__), "..", "store", "config.json"), encoding="utf-8")),
                open(os.path.join(data_dir, "config.json"), "w", encoding="utf-8"),
            )
            env_file = os.path.join(base, ".env")
            # 1) 切到 custom：写 .env 键
            result, restart = patch_section(
                data_dir,
                "asset_paths",
                {
                    "items": [
                        {"env": "MAILBUS_SKILLS_ROOT", "mode": "custom", "custom": r"D:\skills"},
                        {"env": "MAILBUS_RULES_ROOT", "mode": "default"},
                    ]
                },
            )
            self.assertEqual(result["section"], "asset_paths")
            self.assertIn("MAILBUS_SKILLS_ROOT", result["updated"])
            self.assertEqual(restart, ["env"])
            self.assertTrue(os.path.isfile(env_file))
            text = open(env_file, encoding="utf-8").read()
            self.assertIn("MAILBUS_SKILLS_ROOT=D:\\skills", text)
            self.assertNotIn("MAILBUS_RULES_ROOT=", text)
            # 2) 切回 default：删除键
            result, _ = patch_section(
                data_dir,
                "asset_paths",
                {"items": [{"env": "MAILBUS_SKILLS_ROOT", "mode": "default"}]},
            )
            text = open(env_file, encoding="utf-8").read()
            self.assertNotIn("MAILBUS_SKILLS_ROOT=", text)
        finally:
            shutil.rmtree(base, ignore_errors=True)

    def test_patch_asset_paths_rejects_empty_items(self):
        with self.assertRaises(ValueError):
            patch_section(self.tmp, "asset_paths", {"items": []})

    def test_patch_asset_paths_ignores_unknown_env(self):
        base = tempfile.mkdtemp()
        try:
            data_dir = os.path.join(base, "store")
            os.makedirs(data_dir)
            import json as _json
            _json.dump(
                _json.load(open(os.path.join(os.path.dirname(__file__), "..", "store", "config.json"), encoding="utf-8")),
                open(os.path.join(data_dir, "config.json"), "w", encoding="utf-8"),
            )
            env_file = os.path.join(base, ".env")
            result, _ = patch_section(
                data_dir,
                "asset_paths",
                {"items": [{"env": "MAILBUS_UNKNOWN_ROOT", "mode": "custom", "custom": r"D:\x"}]},
            )
            self.assertEqual(result["updated"], [])
            self.assertFalse(os.path.isfile(env_file))
        finally:
            shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
