"""task_completion / recruit push / phantom 相关测试。"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.task_completion import is_task_complete
from lib.phantom_detect import is_phantom_reply_text, check_phantom_completion
from lib.pusher import resolve_cli_chain


TYPES = {
    "hermes_profile": {"push": "legacy"},
    "models": {
        "deepseek-flash": {"hermes_profile": "--model deepseek-chat"},
    },
}


class TestTaskCompletion(unittest.TestCase):
    def test_notice_not_complete_via_replies(self):
        ok, reason = is_task_complete("/tmp", "xiaoqi", {"type": "notice", "id": "m1", "content": "hi"})
        self.assertFalse(ok)
        self.assertEqual(reason, "notice_not_task_complete")

    def test_phantom_notice_reply_exempt(self):
        self.assertFalse(is_phantom_reply_text("ok", msg_type="notice"))


class TestRecruitPushImport(unittest.TestCase):
    def test_resolve_cli_chain_importable_from_pusher(self):
        cfg = {"type": "hermes_profile", "profile": "lingzhao", "models": ["deepseek-flash"]}
        chain = resolve_cli_chain(cfg, TYPES)
        self.assertTrue(chain)


class TestValidateClineCodexDrift(unittest.TestCase):
    def test_cline_on_lingxiao_service_warns(self):
        from lib.agent_adapters import validate_agents

        agents = {
            "lingxiao": {
                "name": "灵霄",
                "type": "cline",
                "docker": {"service": "lingxiao"},
                "models": ["deepseek-flash"],
            }
        }
        errors = validate_agents(agents, TYPES)
        self.assertTrue(any("type=cline" in e and "codex" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
