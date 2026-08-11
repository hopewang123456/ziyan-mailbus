"""V6: enable saga rollback — mocked planes, no Docker.

Contract: mid-enable failure compensates (stop + config restore) with no
half-finished framework entry (no enabled=True / pending_enable leftovers).
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from lib.adapters.plane.mutex import FileMountMutex
from lib.domain.types import PlaneActionResult, ProbeResult


def _fake_plane_bundle(*, start_ok: bool = True, probe_ok: bool = True):
    host = MagicMock()
    container = MagicMock()
    for plane in (host, container):
        plane.start_framework.return_value = PlaneActionResult(
            ok=start_ok, framework="hermes", detail="started" if start_ok else "start_fail"
        )
        plane.probe_framework.return_value = ProbeResult(
            ok=probe_ok, agent_id="hermes", detail="up" if probe_ok else "down"
        )
        plane.stop_framework.return_value = PlaneActionResult(
            ok=True, framework="hermes", detail="stopped"
        )
    bundle = MagicMock()
    bundle.host = host
    bundle.container = container
    bundle.mutex = FileMountMutex({})
    return bundle, container


def _assert_no_half_finished(cfg: dict, framework_id: str = "hermes") -> None:
    entry = (cfg.get("frameworks") or {}).get(framework_id) or {}
    assert entry.get("enabled") is not True, f"half-finished enabled: {entry}"
    assert "pending_enable" not in entry, f"half-finished pending_enable: {entry}"


def run_enable_probe_fail_no_half_finished(data_dir: str) -> dict:
    """Enable with start ok / probe fail → compensated, config clean. Returns result."""
    from lib.application.lifecycle import enable_framework

    bundle, container = _fake_plane_bundle(start_ok=True, probe_ok=False)
    with patch("lib.application.lifecycle.build_planes", return_value=bundle):
        with patch("lib.application.lifecycle.time.sleep", return_value=None):
            result = enable_framework(data_dir, "hermes", mount_mode="container")
    assert result.get("ok") is False
    assert result.get("compensated") is True
    container.stop_framework.assert_called()
    cfg = json.loads(Path(data_dir, "config.json").read_text(encoding="utf-8"))
    _assert_no_half_finished(cfg)
    return result


def run_enable_start_fail_no_half_finished(data_dir: str) -> dict:
    """Enable with start fail → compensated, config clean. Returns result."""
    from lib.application.lifecycle import enable_framework

    bundle, container = _fake_plane_bundle(start_ok=False, probe_ok=True)
    with patch("lib.application.lifecycle.build_planes", return_value=bundle):
        result = enable_framework(data_dir, "hermes", mount_mode="container")
    assert result.get("ok") is False
    assert result.get("compensated") is True
    container.stop_framework.assert_called()
    cfg = json.loads(Path(data_dir, "config.json").read_text(encoding="utf-8"))
    _assert_no_half_finished(cfg)
    return result


class TestV6EnableRollback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        cfg = {
            "frameworks": {},
            "agents": {"ziyan": {"type": "hermes", "enabled": True}},
        }
        (self.data / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_probe_fail_compensates_no_half_finished(self):
        run_enable_probe_fail_no_half_finished(str(self.data))

    def test_start_fail_compensates_no_half_finished(self):
        run_enable_start_fail_no_half_finished(str(self.data))


if __name__ == "__main__":
    unittest.main()
