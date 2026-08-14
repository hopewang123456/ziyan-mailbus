"""platform_probe 平台适配器 — 结构与降级行为测试。"""
from __future__ import annotations

import unittest

from lib.adapters.ops.platform_probe import (
    DockerProbe,
    FrameworkProbe,
    LinuxProbe,
    PlatformProbeAdapter,
    WindowsProbe,
    WslProbe,
    _command_in_container,
    _command_in_path,
    _config_agents,
    get_platform_probe,
)


class TestPlatformProbe(unittest.TestCase):
    def test_adapter_platform_names(self) -> None:
        self.assertEqual(WindowsProbe().platform_name, "win32")
        self.assertEqual(WslProbe().platform_name, "wsl")
        self.assertEqual(LinuxProbe().platform_name, "linux")
        self.assertEqual(DockerProbe().platform_name, "docker")

    def test_get_platform_probe_returns_known(self) -> None:
        for plat, cls in (
            ("win32", WindowsProbe),
            ("wsl", WslProbe),
            ("linux", LinuxProbe),
            ("darwin", LinuxProbe),
            ("docker", DockerProbe),
        ):
            self.assertIsInstance(get_platform_probe(plat), cls)

    def test_framework_probe_fields(self) -> None:
        p = FrameworkProbe("hermes", "agent-a", "win32", True, "detail")
        self.assertEqual(p.framework, "hermes")
        self.assertEqual(p.instance, "agent-a")
        self.assertTrue(p.ok)

    def test_config_agents_empty(self) -> None:
        self.assertEqual(_config_agents(None), {})
        self.assertEqual(_config_agents({"agents": {"a": {}}}), {"a": {}})

    def test_base_probe_is_not_ok(self) -> None:
        base = PlatformProbeAdapter()
        self.assertEqual(base.list_instances(), [])
        p = base.probe("hermes")
        self.assertIsInstance(p, FrameworkProbe)
        self.assertFalse(p.ok)

    def test_framework_for_uses_type(self) -> None:
        adapter = PlatformProbeAdapter()
        self.assertEqual(
            adapter._framework_for({"agents": {"agent-a": {"type": "hermes"}}}, "agent-a"),
            "hermes",
        )
        self.assertEqual(adapter._framework_for(None, "agent-a"), "agent-a")

    def test_command_in_path_no_crash(self) -> None:
        # 任意 framework 名探测不应抛异常（where / command -v 均可失败）
        self.assertIsInstance(_command_in_path("this-framework-should-not-exist-xyz"), bool)
        self.assertIsInstance(_command_in_container("x", ""), bool)


if __name__ == "__main__":
    unittest.main()
