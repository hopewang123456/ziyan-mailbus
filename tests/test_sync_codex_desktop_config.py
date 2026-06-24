"""Codex Browser / 配置同步。"""
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_SYNC_PATH = os.path.join(ROOT, "tools", "sync-codex-desktop-config.py")
_spec = importlib.util.spec_from_file_location("sync_codex_desktop_config", _SYNC_PATH)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)
agent_reasoning_profile = _mod.agent_reasoning_profile


class TestSyncCodexDesktopConfig(unittest.TestCase):
    def test_lingjian_reasoner_defaults(self):
        profile = agent_reasoning_profile("lingjian", {"model": "deepseek-reasoner"})
        self.assertEqual(profile["model"], "deepseek-reasoner")
        self.assertTrue(profile["supports_reasoning_summaries"])
        self.assertEqual(profile["reasoning_summary"], "auto")

    def test_lingxiao_flash_defaults(self):
        profile = agent_reasoning_profile("lingxiao", {"model": "deepseek-v4-flash"})
        self.assertEqual(profile["model"], "deepseek-v4-flash")
        self.assertFalse(profile["supports_reasoning_summaries"])


if __name__ == "__main__":
    unittest.main()
