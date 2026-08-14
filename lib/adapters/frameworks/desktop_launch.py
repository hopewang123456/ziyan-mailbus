"""Mailbus agent Desktop 启动 — 按平台与 agent launch.desktop 配置跳转原生 App。"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from typing import Any, Dict, Optional, Tuple

from lib.domain.errors import Fatal
from lib.infra.utils import json_read

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SYNC_CODEX_SCRIPT = os.path.join(ROOT, "tools", "sync-codex-desktop-config.py")

PS_HELPER = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
CMD_HELPER = "/mnt/c/Windows/System32/cmd.exe"


def _powershell_exe() -> str:
    if sys.platform == "win32":
        windir = os.environ.get("SystemRoot", r"C:\Windows")
        ps = os.path.join(windir, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        if os.path.isfile(ps):
            return ps
    if os.path.isfile(PS_HELPER):
        return PS_HELPER
    return ""


def _docker_argv() -> Optional[list[str]]:
    if shutil.which("docker"):
        return ["docker"]
    wsl = shutil.which("wsl.exe") or shutil.which("wsl")
    if wsl:
        return [wsl, "docker"]
    return None


def _run(cmd: list[str], *, timeout: int = 60, check: bool = False) -> subprocess.CompletedProcess:
    kwargs: dict = {"capture_output": True, "timeout": timeout, "check": check}
    if sys.platform == "win32":
        kwargs["encoding"] = "utf-8"
        kwargs["errors"] = "replace"
    else:
        kwargs["text"] = True
    return subprocess.run(cmd, **kwargs)


def _config_path(data_dir: str) -> str:
    return os.path.join(os.path.abspath(data_dir), "config.json")


def _run_shell(command: str, *, timeout: int = 60) -> subprocess.CompletedProcess:
    if sys.platform == "win32":
        return _run(["powershell", "-NoProfile", "-Command", command], timeout=timeout)
    return _run(["bash", "-lc", command], timeout=timeout)


def load_mailbus_codex(data_dir: str) -> dict:
    cfg = json_read(_config_path(data_dir), {})
    return cfg.get("mailbus_codex") or {}


def merge_launch_desktop(agent_cfg: dict, agent_types: dict) -> dict:
    launch = agent_cfg.get("launch") or {}
    tmpl_name = launch.get("template", "")
    tmpl = (agent_types.get("launch_templates") or {}).get(tmpl_name, {})
    merged = dict(tmpl.get("desktop") or {})
    merged.update(launch.get("desktop") or {})
    return merged


def agent_has_desktop(agent_cfg: dict, agent_types: Optional[dict] = None) -> bool:
    agent_types = agent_types or {}
    desktop = merge_launch_desktop(agent_cfg, agent_types)
    if desktop.get("enabled") is False:
        return False
    if desktop.get("enabled") is True:
        return bool(desktop.get("kind"))
    return bool(desktop.get("kind"))


def resolve_platform(global_cfg: dict) -> str:
    configured = (global_cfg.get("platform") or "auto").strip().lower()
    if configured in ("windows", "linux"):
        return configured
    if sys.platform == "win32":
        return "windows"
    if sys.platform.startswith("linux"):
        return "linux"
    uname = platform.system().lower()
    if uname == "windows":
        return "windows"
    return "linux"


def platform_settings(global_cfg: dict, plat: str) -> dict:
    block = global_cfg.get(plat) or {}
    if isinstance(block, dict):
        return block
    return {}


def _subst(text: str, mapping: dict) -> str:
    out = text
    for key, val in mapping.items():
        out = out.replace("{" + key + "}", str(val))
    return out


def _ensure_codex_gateway(agent_key: str, agent_cfg: dict, desktop: dict, plat_cfg: dict) -> None:
    """尽力确保 DeepSeek 网关容器在跑；失败不阻塞 Desktop 启动。"""
    if not plat_cfg.get("ensure_gateway_container", True):
        return
    docker_argv = _docker_argv()
    if not docker_argv:
        return
    docker = agent_cfg.get("docker") or {}
    service = docker.get("service") or agent_key
    container = f"docker-agents-{service}-1"
    try:
        ps = _run([*docker_argv, "ps", "-q", "-f", f"name=^{container}$"], timeout=20)
        if (ps.stdout or "").strip():
            return
        popen_kw: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if sys.platform == "win32":
            popen_kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen([*docker_argv, "start", container], **popen_kw)
    except (subprocess.TimeoutExpired, OSError, subprocess.SubprocessError):
        return


def _sync_codex_config(agent_key: str, codex_home: str, gateway_port: int, data_dir: str) -> None:
    if not os.path.isfile(SYNC_CODEX_SCRIPT):
        raise FileNotFoundError(f"missing sync script: {SYNC_CODEX_SCRIPT}")
    _run(
        [
            sys.executable,
            SYNC_CODEX_SCRIPT,
            agent_key,
            "--codex-home",
            codex_home,
            "--gateway-port",
            str(gateway_port),
            "--data-dir",
            os.path.abspath(data_dir),
        ],
        timeout=45,
        check=True,
    )


def _launch_windows_codex(codex_cfg: dict) -> None:
    app_id = (codex_cfg.get("app_id") or "").strip()
    command = (codex_cfg.get("command") or "").strip()
    if command:
        _run_shell(command, timeout=30)
        return
    ps_exe = _powershell_exe()
    if not ps_exe:
        raise Fatal(
            "Windows PowerShell unavailable, cannot launch Codex Desktop",
            code="powershell_unavailable",
            zh="Windows PowerShell 不可用，无法启动 Codex Desktop",
        )
    app_id_ps = app_id.replace("'", "''")
    ps = f"""
$ErrorActionPreference = 'Stop'
$appId = '{app_id_ps}'
if (-not $appId) {{
  $app = Get-StartApps | Where-Object {{ $_.Name -match 'Codex' -or $_.AppId -match 'OpenAI.Codex' }} | Select-Object -First 1
  if (-not $app) {{
    throw 'CODEX_DESKTOP_NOT_FOUND'
  }}
  $appId = $app.AppId
}}
Start-Process ("shell:AppsFolder\\" + $appId)
""".strip()
    result = _run([ps_exe, "-NoProfile", "-Command", ps], timeout=30)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        if "CODEX_DESKTOP_NOT_FOUND" in err:
            raise Fatal(
                "Codex Desktop not found. Install with: winget install Codex -s msstore",
                code="codex_desktop_not_found",
                zh="未检测到 Codex Desktop。请先安装：winget install Codex -s msstore",
            )
        raise Fatal(
            err or "Failed to launch Codex Desktop",
            code="codex_desktop_launch_failed",
            zh=err or "启动 Codex Desktop 失败",
        )


def _launch_linux_codex(codex_cfg: dict) -> None:
    command = (codex_cfg.get("command") or "codex-app").strip()
    if command == "auto":
        for cand in ("codex-app", "codex-desktop", "codex"):
            if shutil.which(cand):
                command = cand
                break
        else:
            raise Fatal(
                "Codex Desktop executable not found (codex-app / codex-desktop)",
                code="codex_desktop_missing",
                zh="未找到 Codex Desktop 可执行文件（codex-app / codex-desktop）",
            )
    if "{project_dir}" in command:
        raise Fatal(
            "Linux command requires caller to substitute project_dir",
            code="linux_command_unsubstituted",
            zh="Linux command 需由调用方替换 project_dir",
        )
    _run(["bash", "-lc", command], timeout=30)


def _launch_url(url: str) -> None:
    ps_exe = _powershell_exe()
    if ps_exe:
        safe = url.replace("'", "''")
        _run([ps_exe, "-NoProfile", "-Command", f"Start-Process '{safe}'"], timeout=20)
        return
    if os.path.isfile(CMD_HELPER):
        _run([CMD_HELPER, "/c", "start", "", url], timeout=20)
        return
    if sys.platform == "win32":
        os.startfile(url)  # type: ignore[attr-defined]
        return
    if shutil.which("xdg-open"):
        _run(["xdg-open", url], timeout=20)
        return
    raise Fatal(
        f"Cannot open URL: {url}",
        code="url_open_failed",
        zh=f"无法打开 URL: {url}",
    )


def launch_desktop(agent_key: str, data_dir: str) -> dict:
    cfg = json_read(_config_path(data_dir), {})
    agents = cfg.get("agents") or {}
    if agent_key not in agents:
        raise ValueError(f"unknown agent: {agent_key}")
    agent_cfg = agents[agent_key]
    agent_types = cfg.get("agent_types") or {}
    desktop = merge_launch_desktop(agent_cfg, agent_types)
    if not agent_has_desktop(agent_cfg, agent_types):
        raise ValueError(f"agent '{agent_key}' 未配置 launch.desktop")

    global_cfg = load_mailbus_codex(data_dir)
    plat = resolve_platform(global_cfg)
    plat_cfg = platform_settings(global_cfg, plat)
    kind = (desktop.get("kind") or "").strip()
    launch_cfg = agent_cfg.get("launch") or {}
    browser_cfg = launch_cfg.get("browser") or {}
    gateway_port = int(desktop.get("gateway_port") or browser_cfg.get("gateway_port") or 9220)
    project_dir = (
        desktop.get("project_dir")
        or (plat_cfg.get("default_project_roots") or {}).get(agent_key)
        or plat_cfg.get("default_project_dir")
        or ""
    )
    codex_home = desktop.get("codex_home") or plat_cfg.get("codex_home") or ""

    if kind == "codex_desktop":
        if not codex_home:
            raise ValueError("mailbus_codex.{platform}.codex_home 未配置")
        if plat_cfg.get("sync_on_launch", True):
            _sync_codex_config(agent_key, codex_home, gateway_port, data_dir)
        _ensure_codex_gateway(agent_key, agent_cfg, desktop, plat_cfg)
        codex_desktop_cfg = dict(plat_cfg.get("codex_desktop") or {})
        codex_desktop_cfg.update({k: v for k, v in desktop.items() if k in ("app_id", "command")})
        if plat == "windows":
            _launch_windows_codex(codex_desktop_cfg)
        else:
            cmd = (codex_desktop_cfg.get("command") or "codex-app").strip()
            if project_dir:
                cmd = _subst(cmd, {"project_dir": project_dir, "agent": agent_key})
            _launch_linux_codex({"command": cmd})
        return {
            "agent": agent_key,
            "kind": kind,
            "platform": plat,
            "codex_home": codex_home,
            "gateway_port": gateway_port,
            "project_dir": project_dir,
        }

    if kind == "url":
        url = desktop.get("url") or ""
        if not url:
            raise ValueError("desktop.kind=url 需要 desktop.url")
        url = _subst(url, {"agent": agent_key, "port": gateway_port, "project_dir": project_dir})
        _launch_url(url)
        return {"agent": agent_key, "kind": kind, "platform": plat, "url": url}

    if kind == "command":
        command = desktop.get("command") or plat_cfg.get("command") or ""
        if not command:
            raise ValueError("desktop.kind=command 需要 desktop.command")
        command = _subst(
            command,
            {
                "agent": agent_key,
                "port": gateway_port,
                "project_dir": project_dir,
                "codex_home": codex_home,
            },
        )
        _run_shell(command, timeout=45)
        return {"agent": agent_key, "kind": kind, "platform": plat, "command": command}

    if kind == "claude_interactive":
        from .claude_launch import launch_interactive_desktop

        return launch_interactive_desktop(agent_key, data_dir, desktop)

    raise ValueError(f"unsupported desktop kind: {kind}")
