"""Tests for lib/launch_ports.py"""

from __future__ import annotations

import unittest

from lib.adapters.config.launch_ports import (
    build_browser_url,
    default_port,
    resolve_port,
    resolve_codex_ttyd_port,
)


class LaunchPortsTest(unittest.TestCase):
    def test_hermes_default_lingxi(self):
        self.assertEqual(default_port("lingxi", group="hermes_dashboard"), 9122)

    def test_hermes_custom_override(self):
        cfg = {"type": "hermes_profile", "docker": {"port": 9122}}
        browser = {"kind": "hermes_dashboard", "dashboard_port": 9999}
        self.assertEqual(resolve_port("lingxi", cfg, browser), 9999)

    def test_hermes_docker_port(self):
        cfg = {"type": "hermes_profile", "docker": {"port": 9122}}
        browser = {"kind": "hermes_dashboard"}
        self.assertEqual(resolve_port("lingxi", cfg, browser), 9122)

    def test_hermes_fallback_without_docker(self):
        cfg = {"type": "hermes_profile"}
        browser = {"kind": "hermes_dashboard"}
        self.assertEqual(resolve_port("lingxi", cfg, browser), 9122)

    def test_codex_defaults(self):
        self.assertEqual(default_port("lingxiao", group="codex_web"), 9240)
        self.assertEqual(resolve_codex_ttyd_port("lingxiao", {}), 9250)

    def test_build_browser_url(self):
        cfg = {"type": "hermes_profile", "docker": {"port": 9122}}
        browser = {"kind": "hermes_dashboard", "url": "http://localhost:{port}/chat"}
        url = build_browser_url("lingxi", cfg, browser)
        self.assertEqual(url, "http://localhost:9122/chat")


if __name__ == "__main__":
    unittest.main()
