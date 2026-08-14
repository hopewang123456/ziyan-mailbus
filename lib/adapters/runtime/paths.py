"""Four-end path forms + PathPort adapters."""

from __future__ import annotations

import os
from dataclasses import dataclass

from lib.adapters.frameworks.framework_discovery import CONTAINER_INSTALL_ROOTS
from lib.infra.utils import to_container_store_path, to_wsl_path


def _norm_framework(fw: str) -> str:
    f = (fw or "").strip()
    return "hermes" if f == "hermes_profile" else f


def _host_norm(p: str) -> str:
    if not p:
        return ""
    return os.path.normpath(os.path.expandvars((p or "").replace("\\", "/"))).rstrip("\\/")


def _is_windows_path(p: str) -> bool:
    s = (p or "").replace("\\", "/")
    return len(s) >= 2 and s[1] == ":"


def docker_path_for(
    win_path: str,
    data_dir: str,
    *,
    install_root: str = "",
    framework: str = "",
) -> str:
    dkr = to_container_store_path(data_dir, win_path) if data_dir else win_path
    cont_root = CONTAINER_INSTALL_ROOTS.get(framework) or CONTAINER_INSTALL_ROOTS.get(_norm_framework(framework), "")
    if cont_root:
        host_norm = _host_norm(win_path)
        root_norm = _host_norm(install_root)
        if root_norm and host_norm.lower().startswith(root_norm.lower()):
            rel = host_norm[len(root_norm) :].lstrip("\\/").replace("\\", "/")
            return (cont_root.rstrip("/") + "/" + rel) if rel else cont_root
        return cont_root
    return dkr


def resolve_all_path_forms(
    logical_path: str,
    data_dir: str = "",
    *,
    install_root: str = "",
    framework: str = "",
) -> dict[str, str]:
    """Derive windows/wsl/linux/docker representations from a logical path."""
    win = logical_path
    wsl = to_wsl_path(logical_path) if _is_windows_path(logical_path) else logical_path.replace("\\", "/")
    # linux: posix form — same as wsl mapping when stored as Windows path on dual-boot/mailbus-on-Windows
    linux = wsl if _is_windows_path(logical_path) else logical_path.replace("\\", "/")
    dkr = docker_path_for(logical_path, data_dir, install_root=install_root, framework=framework)
    return {"windows": win, "wsl": wsl, "linux": linux, "docker": dkr}


@dataclass
class _PathPort:
    target: str

    def resolve(
        self,
        logical_path: str,
        *,
        data_dir: str = "",
        install_root: str = "",
        framework: str = "",
    ) -> str:
        forms = resolve_all_path_forms(
            logical_path, data_dir, install_root=install_root, framework=framework
        )
        return forms.get(self.target) or logical_path

    def exists(
        self,
        logical_path: str,
        *,
        data_dir: str = "",
        install_root: str = "",
        framework: str = "",
    ) -> bool:
        # Arch1: existence gate stays host-stat (source of truth on host / Windows view).
        host = logical_path
        try:
            from lib.adapters.config.sync_layers import normalize_host_path

            host = str(normalize_host_path(logical_path))
        except Exception:
            host = logical_path
        return bool(host) and (os.path.isdir(host) or os.path.isfile(host))


@dataclass
class RuntimeAdapter:
    name: str

    @property
    def path(self) -> _PathPort:
        return _PathPort(self.name)


WINDOWS = RuntimeAdapter("windows")
WSL = RuntimeAdapter("wsl")
LINUX = RuntimeAdapter("linux")
DOCKER = RuntimeAdapter("docker")

ADAPTERS: dict[str, RuntimeAdapter] = {
    "windows": WINDOWS,
    "wsl": WSL,
    "linux": LINUX,
    "docker": DOCKER,
}
