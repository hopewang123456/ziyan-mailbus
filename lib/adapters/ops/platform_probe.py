"""诊所平台适配器 — 按当前启动平台探测 Agent 框架实例。

设计目标：mailbus 启动窗口在 windows 时校验 windows / wsl / docker 下存在的
Agent 框架实例；在 linux 时校验 linux 本机 + docker 下实例。各平台实现
共享 ``PlatformProbeAdapter`` 接口，诊所 / doctor 统一通过 ``get_platform_probe()``
获取当前平台适配器，不再散落 wsl/bash 分支。

接口：
  - ``name()``            平台标识（win32 / wsl / linux / darwin / docker）
  - ``list_instances()``  该平台下可探测的 Agent 框架实例列表
  - ``probe(framework, instance="")``  探测单个框架实例是否就绪
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, List

from lib.adapters.plane.platform_runner import (
    docker_ready,
    run,
    running_in_mailbus_docker,
    wsl_exe,
)


@dataclass
class FrameworkProbe:
    framework: str
    instance: str
    platform: str
    ok: bool
    detail: str = ""
    children: List[str] = field(default_factory=list)


class PlatformProbeAdapter:
    """平台探测适配器基类。"""

    platform_name = "generic"

    def list_instances(self, config: dict[str, Any] | None = None) -> list[str]:
        """返回该平台下可探测的 Agent 框架实例（agent key）。"""
        return []

    def probe(self, framework: str, instance: str = "") -> FrameworkProbe:
        """探测单个框架实例是否就绪。子类按平台实现。"""
        return FrameworkProbe(framework, instance, self.platform_name, ok=False)

    def probe_all(self, config: dict[str, Any] | None = None) -> list[FrameworkProbe]:
        out: list[FrameworkProbe] = []
        for inst in self.list_instances(config):
            framework = self._framework_for(config, inst)
            out.append(self.probe(framework, inst))
        return out

    def _framework_for(self, config: dict[str, Any] | None, instance: str) -> str:
        """agent key → framework 探测名（用 config type；未知回落到 key）。"""
        agents = _config_agents(config)
        ac = agents.get(instance) or {}
        return str(ac.get("type") or instance)


def _config_agents(config: dict[str, Any] | None = None) -> dict[str, Any]:
    return (config or {}).get("agents") or {}


def _command_in_path(framework: str) -> bool:
    """本机 PATH 探测（win32 用 where，其余用 bash command -v）。"""
    if sys.platform == "win32":
        r = run(["where", framework], timeout=10)
        return r.returncode == 0 and bool((r.stdout or "").strip())
    r = run(["bash", "-lc", f"command -v {framework} 2>/dev/null || echo missing"], timeout=15)
    return r.returncode == 0 and "missing" not in (r.stdout or "")


def _command_in_wsl(framework: str) -> bool:
    wsl = wsl_exe()
    if not wsl:
        return False
    r = run([wsl, "-e", "bash", "-lc", f"command -v {framework} 2>/dev/null || echo missing"], timeout=20)
    return r.returncode == 0 and "missing" not in (r.stdout or "")


def _command_in_container(framework: str, container: str) -> bool:
    """在容器内探测 CLI（win32 经 WSL 访问 docker）。"""
    if not container:
        return False
    if sys.platform == "win32":
        wsl = wsl_exe()
        if not wsl:
            return False
        cmd = [wsl, "-e", "bash", "-lc",
               f"docker exec {container} sh -c 'command -v {framework} >/dev/null 2>&1 && echo ok'"]
    else:
        cmd = ["docker", "exec", container, "sh", "-c", f"command -v {framework} >/dev/null 2>&1 && echo ok"]
    try:
        r = run(cmd, timeout=20)
        return r.returncode == 0 and "ok" in (r.stdout or "")
    except Exception:
        return False


def _container_for(config: dict[str, Any] | None, framework: str, instance: str) -> str:
    """从 config 解析容器服务名（复用 resolve_container）。"""
    try:
        from lib.adapters.frameworks import resolve_container

        agents = _config_agents(config)
        agent_cfg = agents.get(instance) or {}
        return resolve_container(agent_cfg, instance, framework) or ""
    except Exception:
        return ""


class WindowsProbe(PlatformProbeAdapter):
    """Windows 本机：校验本机进程 / WSL / Docker 三层实例。"""

    platform_name = "win32"

    def list_instances(self, config=None) -> list[str]:
        return sorted(_config_agents(config).keys())

    def probe(self, framework: str, instance: str = "") -> FrameworkProbe:
        inst = instance or framework
        if _command_in_path(framework):
            return FrameworkProbe(framework, inst, self.platform_name, True, f"{framework} in PATH")
        if _command_in_wsl(framework):
            return FrameworkProbe(framework, inst, self.platform_name, True, f"wsl: {framework}")
        container = _container_for(config=None, framework=framework, instance=inst)
        if container and docker_ready() and _command_in_container(framework, container):
            return FrameworkProbe(framework, inst, self.platform_name, True, f"docker:{container}")
        return FrameworkProbe(framework, inst, self.platform_name, False, "not found in win32/wsl/docker")


class WslProbe(PlatformProbeAdapter):
    """WSL 环境：校验 WSL 本机 + Docker 实例。"""

    platform_name = "wsl"

    def list_instances(self, config=None) -> list[str]:
        return sorted(_config_agents(config).keys())

    def probe(self, framework: str, instance: str = "") -> FrameworkProbe:
        inst = instance or framework
        if _command_in_path(framework):
            return FrameworkProbe(framework, inst, self.platform_name, True, f"wsl: {framework}")
        container = _container_for(config=None, framework=framework, instance=inst)
        if container and docker_ready() and _command_in_container(framework, container):
            return FrameworkProbe(framework, inst, self.platform_name, True, f"docker:{container}")
        return FrameworkProbe(framework, inst, self.platform_name, False, "not found in wsl/docker")


class LinuxProbe(PlatformProbeAdapter):
    """Linux 本机：校验本机 + Docker 实例。"""

    platform_name = "linux"

    def list_instances(self, config=None) -> list[str]:
        return sorted(_config_agents(config).keys())

    def probe(self, framework: str, instance: str = "") -> FrameworkProbe:
        inst = instance or framework
        if _command_in_path(framework):
            return FrameworkProbe(framework, inst, self.platform_name, True, f"linux: {framework}")
        container = _container_for(config=None, framework=framework, instance=inst)
        if container and docker_ready() and _command_in_container(framework, container):
            return FrameworkProbe(framework, inst, self.platform_name, True, f"docker:{container}")
        return FrameworkProbe(framework, inst, self.platform_name, False, "not found in linux/docker")


class DockerProbe(PlatformProbeAdapter):
    """mailbus 容器内：校验 docker 服务名可访问的框架实例。"""

    platform_name = "docker"

    def list_instances(self, config=None) -> list[str]:
        return sorted(_config_agents(config).keys())

    def probe(self, framework: str, instance: str = "") -> FrameworkProbe:
        inst = instance or framework
        container = _container_for(config=None, framework=framework, instance=inst)
        if container and docker_ready() and _command_in_container(framework, container):
            return FrameworkProbe(framework, inst, self.platform_name, True, f"docker:{container}")
        if _command_in_path(framework):
            return FrameworkProbe(framework, inst, self.platform_name, True, f"container: {framework}")
        return FrameworkProbe(framework, inst, self.platform_name, False, "not found in docker")


def get_platform_probe(platform: str = "") -> PlatformProbeAdapter:
    """返回当前平台适配器（win32 / wsl / linux / darwin / docker）。"""
    plat = platform or _detect()
    if plat == "win32":
        return WindowsProbe()
    if plat == "wsl":
        return WslProbe()
    if plat == "darwin":
        return LinuxProbe()  # macOS 视作类 linux 本机
    if plat == "docker":
        return DockerProbe()
    return LinuxProbe()


def _detect() -> str:
    if running_in_mailbus_docker():
        return "docker"
    from lib.adapters.plane.platform_runner import detect_platform

    plat = detect_platform()
    return plat


__all__ = [
    "PlatformProbeAdapter",
    "FrameworkProbe",
    "WindowsProbe",
    "WslProbe",
    "LinuxProbe",
    "DockerProbe",
    "get_platform_probe",
]
