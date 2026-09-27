"""scan 推送队列的毒消息隔离（2026-09-21 停摆事故回归）。

事故：容器内 scan 推送 claude 类消息时，`_build_windows_push` 因容器无
PowerShell raise Fatal，异常穿透 `_push_queue` 炸死整个 scan 推送队列，
导致同队列其他 agent（G8 hermes / G10 openclaw）全部堵死、回执停消化。

回归覆盖两点：
1. claude windows 桥在无 PowerShell 环境返回 None（host-only 跳过），
   消息留队列待宿主 scan，不再 raise Fatal；
2. `_push_queue` 对单个 agent 的 resolve/push 异常做隔离——后续 agent
   照常推送，毒消息只计自身失败。
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.domain.errors import Fatal


AGENT_CFG = {
    "type": "claude_code",
    "models": ["deepseek-flash"],
    "push": {"cwd": "/tmp/mbtest"},
}

TYPES = {
    "models": {
        "deepseek-flash": {"claude_code": "--model m-flash"},
    },
}


class TestClaudeHostOnlyBridge(unittest.TestCase):
    """无 PowerShell 环境下 windows 桥必须优雅跳过，不得 Fatal。"""

    def _build(self):
        from lib.adapters.frameworks.claude_launch import build_push_command
        return build_push_command("agent-h", AGENT_CFG, TYPES, "deepseek-flash")

    @patch("lib.adapters.frameworks.claude_launch._powershell_exe", return_value="")
    @patch(
        "lib.adapters.frameworks.claude_launch.load_mailbus_claude",
        return_value={"platform": "windows"},
    )
    def test_windows_bridge_without_powershell_returns_none(self, *_mocks):
        cmd = self._build()
        self.assertIsNone(cmd)

    @patch(
        "lib.adapters.frameworks.claude_launch._powershell_exe",
        return_value="/fake/powershell.exe",
    )
    @patch(
        "lib.adapters.frameworks.claude_launch.load_mailbus_claude",
        return_value={"platform": "windows"},
    )
    def test_windows_bridge_with_powershell_still_builds(self, *_mocks):
        cmd = self._build()
        self.assertIsNotNone(cmd)
        self.assertIn("powershell", cmd.lower())


class TestPushQueueIsolation(unittest.TestCase):
    """单 agent 推送异常不得炸死整个队列。"""

    def _run(self, queue):
        from lib.application.commands.commands import _push_queue

        data_dir = tempfile.mkdtemp(prefix="mb-poison-")
        config = {
            "agents": {
                "poison": {"type": "claude_code"},
                "healthy": {"type": "hermes"},
            },
            "agent_types": {},
        }
        pushed = []

        def fake_resolve(agent_cfg, agent_types, msg, agent_name, **_kw):
            if agent_name == "poison":
                raise Fatal("PowerShell unavailable, cannot bridge Windows Claude Code")
            return "cli-cmd"

        def fake_push(**kw):
            pushed.append(kw.get("agent_name"))
            return []

        with patch(
            "lib.application.commands.commands.resolve_cli_for_message",
            side_effect=fake_resolve,
        ), patch(
            "lib.application.commands.commands.push_messages",
            side_effect=fake_push,
        ):
            failed = _push_queue(data_dir, config, queue, "普通")
        return failed, pushed

    def test_resolve_fatal_does_not_kill_queue(self):
        failed, pushed = self._run(
            {"poison": [{"id": "m1"}], "healthy": [{"id": "m2"}]}
        )
        self.assertEqual(pushed, ["healthy"])
        self.assertEqual(failed, ["m1"])

    def test_push_exception_counts_as_failed(self):
        from lib.application.commands.commands import _push_queue

        data_dir = tempfile.mkdtemp(prefix="mb-poison-")
        config = {
            "agents": {"boom": {"type": "claude_code"}},
            "agent_types": {},
        }
        with patch(
            "lib.application.commands.commands.resolve_cli_for_message",
            return_value="cli-cmd",
        ), patch(
            "lib.application.commands.commands.push_messages",
            side_effect=OSError("spawn failed"),
        ):
            failed = _push_queue(data_dir, config, {"boom": [{"id": "m9"}]}, "普通")
        self.assertEqual(failed, ["m9"])


if __name__ == "__main__":
    unittest.main()
