"""agent_adapters 适配层单元测试。"""
import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.agent_adapters import (
    ADAPTERS,
    resolve_push_cli,
    resolve_interactive_cli,
    validate_agents,
    get_adapter,
)
from lib.pusher import resolve_cli


TYPES = {
    "hermes_profile": {"push": "legacy"},
    "openclaw": {"push": "legacy"},
    "opencode": {"push": "legacy"},
    "cline": {"push": "legacy"},
    "models": {
        "deepseek-flash": {
            "hermes_profile": "--model deepseek-chat",
            "openclaw": "--model deepseek/deepseek-chat",
            "opencode": "--model deepseek/deepseek-chat",
            "cline": "--provider openai-compatible",
        },
    },
}


class TestAgentAdapters(unittest.TestCase):
    def test_hermes_profiles_same_structure(self):
        profiles = ["lingzhao", "lingjin", "lingxi", "lingjian", "lingyan", "lingxun", "lingtuo", "lingzhang"]
        cmds = []
        for p in profiles:
            cfg = {"type": "hermes_profile", "profile": p, "models": ["deepseek-flash"]}
            cmd = resolve_push_cli(p, cfg, TYPES, "deepseek-flash")
            cmds.append(cmd)
            self.assertIn("docker-agents-hermes-1", cmd)
            self.assertIn(f"--profile {p}", cmd)
            self.assertNotIn("--skills", cmd)
            self.assertNotIn("-it", cmd)
        # 除 profile 外结构一致
        normalized = [
            c.replace(f"--profile {p}", "--profile PROFILE")
            for c, p in zip(cmds, profiles)
        ]
        self.assertEqual(len(set(normalized)), 1)

    def test_openclaw_push_uses_agent_id(self):
        cfg = {"type": "openclaw", "agent": "xiaoqi", "models": ["deepseek-flash"]}
        cmd = resolve_push_cli("xiaoqi", cfg, TYPES)
        self.assertIn("docker-agents-openclaw-1", cmd)
        self.assertIn("--agent xiaoqi", cmd)
        self.assertIn("OPENCLAW_STATE_DIR=/workspace/data/.openclaw-xiaoqi", cmd)

    def test_opencode_push(self):
        cfg = {"type": "opencode", "models": ["deepseek-flash"]}
        cmd = resolve_push_cli("dali", cfg, TYPES, "deepseek-flash")
        self.assertIn("docker-agents-dali-1", cmd)
        self.assertIn("opencode run", cmd)
        self.assertIn("--dangerously-skip-permissions", cmd)
        self.assertIn("--dir /mailbus/store", cmd)
        self.assertNotIn("-it", cmd)

    def test_cline_push(self):
        cfg = {
            "type": "cline",
            "provider": "--provider openai-compatible",
            "models": ["deepseek-flash"],
        }
        cmd = resolve_push_cli("lingxiao", cfg, TYPES, "deepseek-flash")
        self.assertIn("docker-agents-lingxiao-1", cmd)
        self.assertIn("bash -lc", cmd)
        self.assertIn("cline", cmd)
        self.assertIn("-P openai-compatible", cmd)
        self.assertIn("-m deepseek-chat", cmd)
        self.assertIn("-c /mailbus/store", cmd)
        self.assertNotIn("-q", cmd)
        self.assertNotIn("hermes", cmd)

    def test_cline_cli_active_detects_push_not_hub(self):
        adapter = get_adapter("cline")
        ps = (
            "root 55 cline-hub-daemon\n"
            "root 99 /usr/local/bin/cline 'mailbus task' -P openai-compatible -m deepseek-chat -t 300\n"
        )
        self.assertTrue(adapter.cli_active_in_ps("lingxiao", {}, ps))
        self.assertFalse(adapter.cli_active_in_ps("lingxiao", {}, "root 55 cline-hub-daemon\n"))

    def test_opencode_cli_active_detects_run(self):
        adapter = get_adapter("opencode")
        ps = "root 88 opencode run 'MSG' --dangerously-skip-permissions\n"
        self.assertTrue(adapter.cli_active_in_ps("dali", {}, ps))
        self.assertFalse(adapter.cli_active_in_ps("dali", {}, "root 1 tail -f /dev/null\n"))

    def test_legacy_cline_override_no_hermes_q(self):
        cfg = {
            "type": "cline",
            "launch": {"cli": {"command": "docker exec docker-agents-lingxiao-1 cline -P openai-compatible"}},
        }
        cmd = resolve_push_cli("lingxiao", cfg, TYPES)
        self.assertIn("'MSG'", cmd)
        self.assertNotIn("-q 'MSG'", cmd)

    def test_interactive_has_tty(self):
        cfg = {"type": "hermes_profile", "profile": "lingxi"}
        cmd = resolve_interactive_cli("lingxi", cfg, TYPES)
        self.assertIn("-it", cmd)
        self.assertIn("--profile lingxi", cmd)

    def test_codex_interactive_cli(self):
        cfg = {
            "type": "codex",
            "model": "deepseek-v4-flash",
            "docker": {"service": "lingxiao"},
            "push": {"cwd": "/mailbus/store"},
        }
        cmd = resolve_interactive_cli("lingxiao", cfg, TYPES)
        self.assertIn("-it", cmd)
        self.assertIn("docker-agents-lingxiao-1", cmd)
        self.assertIn("codex", cmd)
        self.assertIn("deepseek-v4-flash", cmd)

    def test_codex_lingjian_interactive_cli(self):
        cfg = {
            "type": "codex",
            "model": "deepseek-v4-flash",
            "docker": {"service": "lingjian"},
            "push": {"cwd": "/mailbus/store"},
        }
        cmd = resolve_interactive_cli("lingjian", cfg, TYPES)
        self.assertIn("docker-agents-lingjian-1", cmd)
        self.assertIn("codex", cmd)

    def test_claude_code_push_windows(self):
        cfg = {
            "type": "claude_code",
            "models": ["minimax-m2"],
            "push": {"cwd": r"E:\ai_tools"},
        }
        types = {
            **TYPES,
            "models": {
                **TYPES.get("models", {}),
                "minimax-m2": {"claude_code": "--model MiniMax-M2.7"},
            },
        }
        with patch("lib.claude_launch.resolve_claude_platform", return_value="windows"):
            cmd = resolve_push_cli("lingyun", cfg, types, "minimax-m2")
        self.assertIn("claude", cmd)
        self.assertIn("-p", cmd)
        self.assertIn("'MSG'", cmd)
        self.assertIn("acceptEdits", cmd)
        self.assertNotIn("docker exec", cmd)
        self.assertNotIn("-it", cmd)

    def test_claude_code_cli_active(self):
        adapter = get_adapter("claude_code")
        ps = "user 42 claude -p 'task' --permission-mode acceptEdits\n"
        self.assertTrue(adapter.cli_active_in_ps("lingyun", {}, ps))
        self.assertFalse(adapter.cli_active_in_ps("lingyun", {}, "user 1 bash\n"))

    def test_legacy_override_still_works(self):
        cfg = {
            "type": "hermes_profile",
            "profile": "lingxi",
            "launch": {"cli": {"command": "docker exec docker-agents-hermes-1 hermes chat --profile lingxi --yolo"}},
        }
        cmd = resolve_push_cli("lingxi", cfg, TYPES)
        self.assertIn("-q 'MSG'", cmd)

    def test_store_config_valid(self):
        root = os.path.join(os.path.dirname(__file__), "..", "store", "config.json")
        if not os.path.isfile(root):
            self.skipTest("no store config")
        data = json.load(open(root, encoding="utf-8"))
        errors = validate_agents(data.get("agents", {}), data.get("agent_types", {}))
        self.assertEqual(errors, [])

    def test_resolve_cli_wrapper(self):
        cfg = {"type": "hermes_profile", "profile": "lingxi"}
        cmd = resolve_cli(cfg, TYPES, agent_name="lingxi")
        self.assertIn("--profile lingxi", cmd)

    def test_all_types_have_adapter(self):
        for t in ("hermes_profile", "openclaw", "cline", "opencode", "codex", "claude_code", "none"):
            self.assertIsNotNone(get_adapter(t))


if __name__ == "__main__":
    unittest.main()
