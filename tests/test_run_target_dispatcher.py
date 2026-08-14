"""Arch1: RunTargetDispatcher + distro + cross-boundary tests."""

from __future__ import annotations

import unittest

from lib.adapters.runtime.boundary import is_cross_boundary, loopback_safe_for_peer, peer_host_hint
from lib.adapters.runtime.dispatcher import RunTargetError, dispatch, normalize_run_target, path_forms_for
from lib.adapters.runtime.distro import CENTOS, UBUNTU, detect_distro


class TestNormalizeAndDispatch(unittest.TestCase):
    def test_normalize_compat(self):
        self.assertEqual(normalize_run_target(""), "windows")
        self.assertEqual(normalize_run_target("window"), "windows")
        self.assertEqual(normalize_run_target("LINUX"), "linux")

    def test_dispatch_hermes_linux(self):
        ad = dispatch("linux", "hermes")
        self.assertEqual(ad.name, "linux")

    def test_dispatch_cursor_rejects_docker(self):
        with self.assertRaises(RunTargetError):
            dispatch("docker", "cursor")

    def test_path_forms_have_four_keys(self):
        forms = path_forms_for(r"Z:\hermes-data\.hermes", "Z:/mailbus/store", framework="hermes")
        self.assertEqual(set(forms), {"windows", "wsl", "linux", "docker"})
        self.assertTrue(forms["wsl"].startswith("/mnt/"))
        self.assertIn("hermes", forms["docker"])


class TestDistro(unittest.TestCase):
    def test_ubuntu(self):
        p = detect_distro('ID=ubuntu\nID_LIKE=debian\n')
        self.assertEqual(p.id, UBUNTU.id)
        self.assertEqual(p.family, "debian")

    def test_centos(self):
        p = detect_distro('ID=centos\nID_LIKE="rhel fedora"\n')
        self.assertEqual(p.id, CENTOS.id)

    def test_rocky_as_centos_family(self):
        p = detect_distro('ID=rocky\nID_LIKE="rhel centos fedora"\n')
        self.assertEqual(p.family, "rhel")


class TestBoundary(unittest.TestCase):
    def test_wsl_windows_cross(self):
        self.assertTrue(is_cross_boundary("windows", "wsl"))
        self.assertFalse(loopback_safe_for_peer("windows", "wsl"))
        self.assertEqual(peer_host_hint("windows", "wsl", wsl_ip="172.28.1.2"), "172.28.1.2")

    def test_same_side_loopback_ok(self):
        self.assertFalse(is_cross_boundary("windows", "windows"))
        self.assertTrue(loopback_safe_for_peer("docker", "docker"))


if __name__ == "__main__":
    unittest.main()
