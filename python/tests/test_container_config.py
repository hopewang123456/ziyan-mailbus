"""Wave7: adapters.container helpers baseline (pytest style)."""
from __future__ import annotations

from unittest import mock

from lib.adapters.container import privilege
from lib.adapters.container.openclaw_profiles import PROFILE_PORTS


def test_profile_ports():
    assert "agent-m" in PROFILE_PORTS
    assert "agent-l" in PROFILE_PORTS
    assert isinstance(PROFILE_PORTS["agent-m"], int)


def test_to_container_mailbus_path():
    with mock.patch.object(privilege, "MAILBUS_ROOT_STR", r"<MAILBUS_ROOT>"):
        with mock.patch.object(privilege, "_mailbus_wsl_prefix", return_value="/mnt/mailbus/"):
            p = privilege._to_container_mailbus_path(r"<MAILBUS_ROOT>\store\config.json")
            assert p.startswith("/mailbus/") or "config.json" in p


def test_host_path_under_mailbus():
    with mock.patch.object(privilege, "MAILBUS_ROOT_STR", r"<MAILBUS_ROOT>"):
        with mock.patch.object(privilege, "_mailbus_wsl_prefix", return_value="/mnt/mailbus/"):
            assert privilege._host_path_under_mailbus(r"<MAILBUS_ROOT>\store\x")
