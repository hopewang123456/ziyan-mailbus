"""Wave1.5 plane + lifecycle saga (mocked planes, no Docker)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from lib.adapters.plane.mutex import FileMountMutex
from lib.domain.errors import Fatal
from lib.domain.types import PlaneActionResult, ProbeResult


class TestMountMutex(unittest.TestCase):
    def test_blocks_switch_while_enabled(self):
        m = FileMountMutex({"hermes": {"enabled": True, "mount_mode": "container"}})
        with self.assertRaises(Fatal):
            m.assert_exclusive("hermes", "host")

    def test_same_mount_ok(self):
        m = FileMountMutex({"hermes": {"enabled": True, "mount_mode": "container"}})
        m.assert_exclusive("hermes", "container")


class TestEnableDisableSaga(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        cfg = {
            "frameworks": {},
            "agents": {"mailbus": {"type": "hermes", "enabled": True}},
        }
        (self.data / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _fake_planes(self, start_ok=True, probe_ok=True, stop_ok=True):
        host = MagicMock()
        container = MagicMock()
        for plane in (host, container):
            plane.start_framework.return_value = PlaneActionResult(
                ok=start_ok, framework="hermes", detail="started" if start_ok else "fail"
            )
            plane.probe_framework.return_value = ProbeResult(
                ok=probe_ok, agent_id="hermes", detail="up" if probe_ok else "down"
            )
            plane.stop_framework.return_value = PlaneActionResult(
                ok=stop_ok, framework="hermes", detail="stopped"
            )
        mutex = FileMountMutex({})
        bundle = MagicMock()
        bundle.host = host
        bundle.container = container
        bundle.mutex = mutex
        return bundle, host, container

    def test_enable_container_calls_container_plane(self):
        from lib.application.lifecycle import enable_framework

        bundle, host, container = self._fake_planes()
        with patch("lib.application.lifecycle.build_planes", return_value=bundle):
            r = enable_framework(str(self.data), "hermes", mount_mode="container")
        self.assertTrue(r["ok"])
        container.start_framework.assert_called_once_with("hermes")
        host.start_framework.assert_not_called()
        cfg = json.loads((self.data / "config.json").read_text(encoding="utf-8"))
        self.assertTrue(cfg["frameworks"]["hermes"]["enabled"])
        self.assertNotIn("pending_enable", cfg["frameworks"]["hermes"])

    def test_enable_probe_fail_compensates(self):
        from lib.application.lifecycle import enable_framework

        bundle, _host, container = self._fake_planes(start_ok=True, probe_ok=False)
        with patch("lib.application.lifecycle.build_planes", return_value=bundle):
            with patch("lib.application.lifecycle.time.sleep", return_value=None):
                r = enable_framework(str(self.data), "hermes", mount_mode="container")
        self.assertFalse(r["ok"])
        self.assertTrue(r.get("compensated"))
        container.stop_framework.assert_called()
        cfg = json.loads((self.data / "config.json").read_text(encoding="utf-8"))
        entry = cfg["frameworks"].get("hermes") or {}
        self.assertNotEqual(entry.get("enabled"), True)

    def test_disable_calls_stop(self):
        from lib.application.lifecycle import disable_framework

        cfg = {
            "frameworks": {"hermes": {"enabled": True, "mount_mode": "host"}},
            "agents": {},
        }
        (self.data / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        bundle, host, container = self._fake_planes()
        with patch("lib.application.lifecycle.build_planes", return_value=bundle):
            r = disable_framework(str(self.data), "hermes")
        self.assertTrue(r["ok"])
        host.stop_framework.assert_called_once_with("hermes")
        container.stop_framework.assert_not_called()


class TestHostPlaneWhitelist(unittest.TestCase):
    def test_rejects_shell_string_start_cmd(self):
        from lib.adapters.plane.host import HostPlane

        with tempfile.TemporaryDirectory() as tmp:
            cfg = {"frameworks": {"x": {"start_cmd": "echo hi && true", "enabled": True}}}
            Path(tmp, "config.json").write_text(json.dumps(cfg), encoding="utf-8")
            plane = HostPlane(tmp)
            # string start_cmd ignored → noop ok
            r = plane.start_framework("x")
            self.assertTrue(r.ok)
            self.assertEqual(r.detail, "no_host_start_cmd")


if __name__ == "__main__":
    unittest.main()
