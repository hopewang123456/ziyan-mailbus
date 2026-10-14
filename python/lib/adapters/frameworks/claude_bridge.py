"""Claude Code 交互/启动桥 — interactive CLI、desktop launch、进程活性探测。"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from typing import Optional

from lib.domain.errors import Fatal
from lib.infra.clock import now_dt, now_ts, now_utc_dt
from lib.infra.constants import PROJECT_ROOT_STR
from lib.infra.utils import json_read, json_write, to_wsl_path
from lib.infra.utils import no_window_creationflags
from lib.adapters.frameworks.claude_env import (
    PS_HELPER, ROOT, _bash_single_quote, _default_data_dir, _powershell_env_from_settings, _powershell_path_prefix, _ps_escape, _running_in_mailbus_docker, _to_powershell_path, _use_windows_claude_in_wsl, _wsl_exe, ensure_claude_agent_settings, platform_settings, resolve_claude_bin, resolve_claude_home, resolve_claude_plat_cfg, resolve_claude_workspace, resolve_project_dir, resolve_windows_claude_bin,
)
from lib.adapters.frameworks import claude_env
from lib.adapters.frameworks.claude_push import (
    _claude_push_flags, _interactive_claude_flags,
)


LAUNCH_QUEUE_PREFIX = "__launch_queue__:"


def _sync_claude_agent_context(agent_name: str, data_dir: str) -> None:
    """Deprecated: profile sync runs via team-pack/tools/sync-team-pack.py at agent startup."""
    return


def _build_interactive_ps_inner(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    data_dir: str,
) -> str:
    """PowerShell -Command 内联脚本（PATH + env + cd + claude）。"""
    global_cfg = claude_env.load_mailbus_claude(data_dir)
    _, plat_cfg = resolve_claude_plat_cfg(global_cfg)
    claude_home = resolve_claude_home(plat_cfg, agent_name)
    workspace = resolve_claude_workspace(agent_cfg, plat_cfg, agent_name)
    workspace_ps = _to_powershell_path(workspace)
    claude_home_ps = _to_powershell_path(claude_home)
    cli_flags = _interactive_claude_flags(agent_name, agent_cfg, agent_types)
    agent_label = (agent_cfg.get("name") or agent_name).strip()

    ensure_claude_agent_settings(agent_name, data_dir)
    env_prefix = _powershell_env_from_settings(agent_name, data_dir)
    claude_bin = resolve_windows_claude_bin(plat_cfg)
    claude_inv = (
        f"& '{_ps_escape(claude_bin)}' {cli_flags}"
        if len(claude_bin) >= 2 and claude_bin[1] == ":"
        else f"& {claude_bin} {cli_flags}"
    )
    return (
        f"{_powershell_path_prefix()}"
        f"{env_prefix}"
        f"$env:CLAUDE_CONFIG_DIR='{_ps_escape(claude_home_ps)}'; "
        f"Set-Location '{_ps_escape(workspace_ps)}'; "
        f"Write-Host '=== mailbus agent: {agent_label} ({agent_name}) ===' -ForegroundColor Cyan; "
        f"{claude_inv}"
    )


def _spawn_powershell_interactive(inner: str) -> None:
    """弹出新的 Windows PowerShell 窗口执行 inner 脚本。"""
    ps_exe = claude_env._powershell_exe()
    if not ps_exe:
        raise Fatal(
            "PowerShell unavailable",
            code="powershell_unavailable",
            zh="PowerShell 不可用",
        )
    if sys.platform == "win32":
        subprocess.Popen(
            [ps_exe, "-NoProfile", "-NoExit", "-Command", inner],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        return
    win_ps = PS_HELPER if os.path.isfile(PS_HELPER) else ps_exe
    win_path = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    arg_inner = inner.replace("'", "''")
    starter = (
        f"Start-Process -FilePath '{win_path}' "
        f"-ArgumentList '-NoExit','-NoProfile','-Command','{arg_inner}'"
    )
    subprocess.run([win_ps, "-NoProfile", "-Command", starter], timeout=30, check=False)


def enqueue_launch_queue(cmd: str, title: str, *, mode: str = "") -> bool:
    """Docker 内经 launch-queue 让 WSL 宿主机执行命令（与 launch_agent.py 同路径）。"""
    candidates = [
        os.environ.get("MAILBUS_LAUNCH_QUEUE", "").strip(),
        "/mailbus/run/launch-queue",
        os.path.join(ROOT, "run", "launch-queue"),
    ]
    safe_title = re.sub(r"[^\w.-]+", "-", (title or "push").strip())[:40] or "push"
    for queue_dir in candidates:
        if not queue_dir:
            continue
        try:
            os.makedirs(queue_dir, exist_ok=True)
            path = os.path.join(queue_dir, f"{safe_title}-{int(now_ts())}.launch")
            with open(path, "w", encoding="utf-8") as f:
                f.write((cmd or "").strip() + "\n")
                f.write(safe_title + "\n")
                if mode:
                    f.write(mode.strip() + "\n")
            try:
                os.chmod(path, 0o666)
            except OSError:
                pass
            return True
        except OSError:
            continue
    return False


def _build_docker_queue_push(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    model_alias: Optional[str],
    *,
    data_dir: str,
) -> str:
    """Docker scheduler scan：经 launch-queue 在 WSL 宿主机跑 PowerShell claude -p。"""
    global_cfg = claude_env.load_mailbus_claude(data_dir)
    plat_cfg = platform_settings(global_cfg, "windows")
    claude_bin = resolve_windows_claude_bin(plat_cfg)
    claude_home = resolve_claude_home(plat_cfg, agent_name)
    project_dir = resolve_project_dir(agent_cfg, plat_cfg, agent_name)
    flags = _claude_push_flags(agent_name, agent_cfg, agent_types, model_alias)
    ps_inner = (
        _powershell_path_prefix()
        + f"$env:USERPROFILE = Split-Path -Parent '{_ps_escape(claude_home)}'; "
        f"Set-Location '{_ps_escape(project_dir)}'; "
        f"& {claude_bin} {flags}"
    )
    ps_exe = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
    wsl_cmd = (
        f"nohup {ps_exe} -NoProfile -Command {_bash_single_quote(ps_inner)} "
        f">> /tmp/mailbus-push-{agent_name}.log 2>&1 &"
    )
    return f"{LAUNCH_QUEUE_PREFIX}{wsl_cmd}"


def build_interactive_command(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    *,
    data_dir: str | None = None,
) -> str:
    dd = data_dir or _default_data_dir()
    _sync_claude_agent_context(agent_name, dd)
    global_cfg = claude_env.load_mailbus_claude(dd)
    plat, plat_cfg = resolve_claude_plat_cfg(global_cfg)
    claude_bin = resolve_claude_bin(plat_cfg)
    claude_home = resolve_claude_home(plat_cfg, agent_name)
    workspace = resolve_claude_workspace(agent_cfg, plat_cfg, agent_name)
    cli_flags = _interactive_claude_flags(agent_name, agent_cfg, agent_types)

    if plat == "windows":
        inner = _build_interactive_ps_inner(agent_name, agent_cfg, agent_types, dd)
        ps_exe = claude_env._powershell_exe()
        if sys.platform == "win32":
            return f'"{ps_exe}" -NoProfile -NoExit -Command "{inner}"'
        return f"{_bash_single_quote(ps_exe)} -NoProfile -NoExit -Command {_bash_single_quote(inner)}"

    inner = (
        f"cd {shlex.quote(to_wsl_path(workspace))} && "
        f"CLAUDE_CONFIG_DIR={shlex.quote(to_wsl_path(claude_home))} "
        f"AGENTMEMORY_URL=http://127.0.0.1:3111 "
        f"{shlex.quote(claude_bin if '/' in claude_bin else '/mnt/<DRIVE>/nodejs/node_global/claude')} {cli_flags}"
    )
    if claude_env._runtime_os() == "windows":
        wsl = _wsl_exe()
        return f"{shlex.quote(wsl)} -e bash -lc {_bash_single_quote(inner)}"
    return f"bash -lc {_bash_single_quote(inner)}"


def build_interactive_shell_inner(
    agent_name: str,
    data_dir: str,
    *,
    platform: str = "linux",
) -> str:
    """WSL/ttyd 内直接执行的 bash 一行命令（无 PowerShell 包装）。"""
    cfg = json_read(os.path.join(os.path.abspath(data_dir), "config.json"), {})
    agents = cfg.get("agents") or {}
    if agent_name not in agents:
        raise ValueError(f"unknown agent: {agent_name}")
    agent_cfg = agents[agent_name]
    agent_types = cfg.get("agent_types") or {}
    global_cfg = claude_env.load_mailbus_claude(data_dir)
    use_windows = _use_windows_claude_in_wsl(global_cfg)
    _, plat_cfg = resolve_claude_plat_cfg(global_cfg)
    claude_home = resolve_claude_home(plat_cfg, agent_name)
    workspace = resolve_claude_workspace(agent_cfg, plat_cfg, agent_name)
    cli_flags = _interactive_claude_flags(agent_name, agent_cfg, agent_types)
    agent_label = (agent_cfg.get("name") or agent_name).strip()

    _sync_claude_agent_context(agent_name, data_dir)

    if use_windows:
        ps_exe = PS_HELPER if os.path.isfile(PS_HELPER) else "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
        inner = _build_interactive_ps_inner(agent_name, agent_cfg, agent_types, data_dir)
        return f"{shlex.quote(ps_exe)} -NoProfile -NoExit -Command {shlex.quote(inner)}"

    project_dir = to_wsl_path(workspace)
    claude_home_wsl = to_wsl_path(claude_home)
    claude_bin = resolve_claude_bin(plat_cfg)
    return (
        f"echo '=== mailbus agent: {agent_label} ({agent_name}) ==='; "
        f"cd {shlex.quote(project_dir)} && "
        f"CLAUDE_CONFIG_DIR={shlex.quote(claude_home_wsl)} "
        f"AGENTMEMORY_URL=http://127.0.0.1:3111 "
        f"exec {shlex.quote(claude_bin)} {cli_flags}"
    )


def host_ps_output() -> str:
    from lib.infra.utils import no_window_creationflags

    try:
        if sys.platform == "win32":
            ps = claude_env._powershell_exe()
            if ps:
                r = subprocess.run(
                    [ps, "-NoProfile", "-Command",
                     "Get-CimInstance Win32_Process | Select-Object -ExpandProperty CommandLine"],
                    capture_output=True,
                    text=True,
                    timeout=12,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=no_window_creationflags(),
                )
                if r.returncode == 0:
                    return r.stdout or ""
        r = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if r.returncode == 0:
            return r.stdout or ""
    except Exception:
        pass
    return ""


def host_cli_active(ps_output: str) -> bool:
    noise = ("grep", "Get-CimInstance", "powershell -NoProfile")
    pat = re.compile(r"\bclaude\b.*(-p\b|--print\b)|(-p\b|--print\b).*\bclaude\b")
    for line in ps_output.splitlines():
        low = line.lower()
        if any(n in low for n in noise):
            continue
        if pat.search(line):
            return True
    return False


def launch_interactive_desktop(agent_key: str, data_dir: str, desktop: dict) -> dict:
    cfg = json_read(os.path.join(os.path.abspath(data_dir), "config.json"), {})
    agents = cfg.get("agents") or {}
    if agent_key not in agents:
        raise ValueError(f"unknown agent: {agent_key}")
    agent_cfg = agents[agent_key]
    agent_types = cfg.get("agent_types") or {}
    global_cfg = claude_env.load_mailbus_claude(data_dir)
    plat = claude_env.resolve_claude_platform(global_cfg)
    plat_cfg = platform_settings(global_cfg, plat)
    project_dir = (
        desktop.get("project_dir")
        or resolve_project_dir(agent_cfg, plat_cfg, agent_key)
    )
    claude_bin = resolve_claude_bin(plat_cfg)
    cmd = build_interactive_command(agent_key, agent_cfg, agent_types, data_dir=data_dir)

    if plat == "windows":
        ps_exe = claude_env._powershell_exe()
        if not ps_exe:
            raise Fatal(
                "PowerShell unavailable",
                code="powershell_unavailable",
                zh="PowerShell 不可用",
            )
        ps_script = f"Start-Process -FilePath '{_ps_escape(ps_exe)}' -ArgumentList '-NoExit','-NoProfile','-Command','Set-Location ''{_ps_escape(project_dir)}''; {claude_bin}'"
        subprocess.run([ps_exe, "-NoProfile", "-Command", ps_script], timeout=30, check=False)
    else:
        term_cmds = [
            f"gnome-terminal -- bash -lc {shlex.quote(cmd)}",
            f"xterm -e bash -lc {shlex.quote(cmd)}",
            cmd,
        ]
        launched = False
        for tc in term_cmds:
            try:
                subprocess.run(["bash", "-lc", tc], timeout=30, check=False)
                launched = True
                break
            except Exception:
                continue
        if not launched:
            raise Fatal(
                "Failed to launch interactive Claude Code terminal",
                code="claude_terminal_launch_failed",
                zh="无法启动交互式 Claude Code 终端",
            )

    return {
        "agent": agent_key,
        "kind": "claude_interactive",
        "platform": plat,
        "project_dir": project_dir,
        "command": cmd,
    }


def launch_claude_cli(agent_key: str, data_dir: str) -> dict:
    """启动 Claude Code 交互 CLI（Windows/WSL 窗口或 Docker launch-queue）。"""
    cfg = json_read(os.path.join(os.path.abspath(data_dir), "config.json"), {})
    agents = cfg.get("agents") or {}
    if agent_key not in agents:
        raise ValueError(f"unknown agent: {agent_key}")
    agent_cfg = agents[agent_key]
    agent_types = cfg.get("agent_types") or {}
    cmd = build_interactive_command(agent_key, agent_cfg, agent_types, data_dir=data_dir)

    if _running_in_mailbus_docker():
        if not enqueue_launch_queue(cmd, agent_key, mode="interactive"):
            raise Fatal(
                "launch queue write failed",
                code="launch_queue_failed",
                zh="launch queue 写入失败",
            )
        return {"agent": agent_key, "mode": "cli", "status": "queued", "command": cmd}

    global_cfg = claude_env.load_mailbus_claude(data_dir)
    plat = claude_env.resolve_claude_platform(global_cfg)
    if plat == "windows" or sys.platform == "win32":
        inner = _build_interactive_ps_inner(agent_key, agent_cfg, agent_types, data_dir)
        _spawn_powershell_interactive(inner)
    elif _wsl_exe() and sys.platform == "win32":
        subprocess.Popen([_wsl_exe(), "-e", "bash", "-lc", cmd], start_new_session=True)
    else:
        subprocess.Popen(["bash", "-lc", cmd], start_new_session=True)

    return {
        "agent": agent_key,
        "mode": "cli",
        "status": "ok",
        "platform": plat,
        "command": cmd,
    }
