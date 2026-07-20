"""Claude Code 浏览器启动 — WSL ttyd Web 终端（DeepSeek/MiniMax 路由）。"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request
from typing import Any, Dict

from .claude_launch import (
    load_mailbus_claude,
    platform_settings,
    resolve_claude_platform,
    resolve_ttyd_bin,
)
from .utils import json_read, to_wsl_path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
START_SCRIPT = os.path.join(ROOT, "tools", "start-claude-web.sh")


def _config_path(data_dir: str) -> str:
    return os.path.join(os.path.abspath(data_dir), "config.json")


def merge_browser_cfg(agent_key: str, data_dir: str) -> dict:
    cfg = json_read(_config_path(data_dir), {})
    agents = cfg.get("agents") or {}
    if agent_key not in agents:
        raise ValueError(f"unknown agent: {agent_key}")
    agent_cfg = agents[agent_key]
    agent_types = cfg.get("agent_types") or {}
    launch = agent_cfg.get("launch") or {}
    tmpl_name = launch.get("template", "")
    tmpl = (agent_types.get("launch_templates") or {}).get(tmpl_name, {})
    merged = dict(tmpl.get("browser") or {})
    merged.update(launch.get("browser") or {})
    return merged


def resolve_browser_port(agent_key: str, data_dir: str, browser_cfg: dict | None = None) -> int:
    browser_cfg = browser_cfg if browser_cfg is not None else merge_browser_cfg(agent_key, data_dir)
    raw = browser_cfg.get("web_port") or browser_cfg.get("port") or ""
    if raw:
        return int(str(raw).strip())
    global_cfg = load_mailbus_claude(data_dir)
    plat = resolve_claude_platform(global_cfg)
    plat_cfg = platform_settings(global_cfg, plat)
    ports = plat_cfg.get("browser_ports") or {}
    if agent_key in ports:
        return int(ports[agent_key])
    return 9260


def resolve_browser_url(agent_key: str, data_dir: str, browser_cfg: dict | None = None) -> str:
    browser_cfg = browser_cfg if browser_cfg is not None else merge_browser_cfg(agent_key, data_dir)
    port = resolve_browser_port(agent_key, data_dir, browser_cfg)
    url = (browser_cfg.get("url") or "http://127.0.0.1:{port}/").strip()
    url = url.replace("{port}", str(port)).replace("{agent}", agent_key)
    if sys.platform == "win32":
        wsl_ip = _wsl_primary_ip()
        if wsl_ip and "127.0.0.1" in url:
            return url.replace("127.0.0.1", wsl_ip)
    return url


def _wsl_exe() -> str:
    return shutil.which("wsl.exe") or shutil.which("wsl") or ""


def _powershell_exe() -> str:
    if sys.platform == "win32":
        windir = os.environ.get("SystemRoot", r"C:\Windows")
        ps = os.path.join(windir, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        if os.path.isfile(ps):
            return ps
    ps_helper = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
    if os.path.isfile(ps_helper):
        return ps_helper
    return ""


def _in_wsl_linux() -> bool:
    if not sys.platform.startswith("linux"):
        return False
    try:
        with open("/proc/version", encoding="utf-8", errors="replace") as fh:
            return "microsoft" in fh.read().lower()
    except OSError:
        return False


def _run_wsl_bash(inner: str, *, timeout: int = 120) -> subprocess.CompletedProcess:
    """在 Windows 宿主经 wsl.exe 执行；已在 WSL 内则直接 bash。"""
    if sys.platform == "win32":
        wsl = _wsl_exe()
        if not wsl:
            raise RuntimeError("wsl.exe 不可用，无法启动 Claude ttyd")
        return _run([wsl, "-e", "bash", "-lc", inner], timeout=timeout)
    if _in_wsl_linux():
        return _run(["bash", "-lc", inner], timeout=timeout)
    wsl = _wsl_exe()
    if wsl:
        return _run([wsl, "-e", "bash", "-lc", inner], timeout=timeout)
    return _run(["bash", "-lc", inner], timeout=timeout)


def _run(cmd: list[str], *, timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        timeout=timeout,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _wsl_primary_ip() -> str:
    wsl = _wsl_exe()
    if not wsl:
        return ""
    try:
        r = _run([wsl, "-e", "bash", "-lc", "hostname -I 2>/dev/null | awk '{print $1}'"], timeout=15)
        if r.returncode != 0:
            return ""
        ip = (r.stdout or "").strip().split()[0] if (r.stdout or "").strip() else ""
        if ip and re.match(r"^\d+\.\d+\.\d+\.\d+$", ip):
            return ip
    except (subprocess.TimeoutExpired, OSError):
        pass
    return ""


def _running_in_mailbus_docker() -> bool:
    from .platform_runner import running_in_mailbus_docker

    return running_in_mailbus_docker()


def _resolve_ttyd_for_launch() -> str:
    """Docker 内 mailbus 无 ttyd，改由 WSL 宿主解析。"""
    if _running_in_mailbus_docker():
        r = _run_wsl_bash("command -v ttyd 2>/dev/null || ls /usr/bin/ttyd 2>/dev/null || true", timeout=15)
        path = (r.stdout or "").strip().splitlines()[-1].strip() if (r.stdout or "").strip() else ""
        if path and path.startswith("/"):
            return path
    return resolve_ttyd_bin()


def _http_ready(url: str, timeout: float = 2.0) -> bool:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status in (200, 401, 403)
    except Exception:
        return False


def _http_ready_on_port(port: int) -> bool:
    """探测 ttyd/codex 端口：localhost、WSL IP、Docker 宿主 host.docker.internal。"""
    hosts = ["127.0.0.1"]
    if _running_in_mailbus_docker():
        hosts.append("host.docker.internal")
    wsl_ip = _wsl_primary_ip()
    if wsl_ip:
        hosts.append(wsl_ip)
    for host in hosts:
        if _http_ready(f"http://{host}:{port}/"):
            return True
    wsl = _wsl_exe()
    if wsl:
        try:
            r = _run(
                [wsl, "-e", "bash", "-lc", f"curl -sf -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{port}/"],
                timeout=8,
            )
            code = (r.stdout or "").strip()
            if code in ("200", "401", "403"):
                return True
        except (subprocess.TimeoutExpired, OSError):
            pass
    return False


def _tmux_session_ok(agent_key: str) -> bool:
    session = f"claude-{agent_key}"
    try:
        r = _run_wsl_bash(f"tmux has-session -t {shlex.quote(session)} 2>/dev/null", timeout=10)
        return r.returncode == 0
    except (RuntimeError, subprocess.TimeoutExpired, OSError):
        return False


def _format_start_error(result: subprocess.CompletedProcess) -> str:
    err = (result.stderr or result.stdout or "").strip()
    if not err:
        return "start-claude-web.sh failed"
    lines = [ln.strip() for ln in err.splitlines() if ln.strip()]
    for ln in reversed(lines):
        if ln.startswith("[claude-web]") or ln.startswith("[ERROR]") or "ttyd" in ln.lower():
            return ln
    return lines[-1] if lines else "start-claude-web.sh failed"


def ensure_claude_web(agent_key: str, data_dir: str, *, wait_seconds: int = 15) -> dict:
    if not os.path.isfile(START_SCRIPT):
        raise FileNotFoundError(f"missing start script: {START_SCRIPT}")

    browser_cfg = merge_browser_cfg(agent_key, data_dir)
    port = resolve_browser_port(agent_key, data_dir, browser_cfg)
    url = resolve_browser_url(agent_key, data_dir, browser_cfg)
    data_dir_abs = os.path.abspath(data_dir)
    wsl_data = to_wsl_path(data_dir_abs)
    wsl_script = to_wsl_path(os.path.abspath(START_SCRIPT))

    if _running_in_mailbus_docker():
        ttyd_wsl = "/usr/bin/ttyd"
    else:
        try:
            ttyd_wsl = to_wsl_path(_resolve_ttyd_for_launch())
        except RuntimeError as exc:
            raise RuntimeError(str(exc)) from exc

    inner = (
        f"export LANG=C.UTF-8 LC_ALL=C.UTF-8 TTYD_BIN={shlex.quote(ttyd_wsl)}; "
        f"bash {shlex.quote(wsl_script)} {shlex.quote(agent_key)} {port} {shlex.quote(wsl_data)}"
    )

    if _http_ready_on_port(port) and _tmux_session_ok(agent_key):
        return {"agent": agent_key, "url": url, "port": port, "ready": True, "started": False}

    if _running_in_mailbus_docker():
        from .claude_launch import enqueue_launch_queue

        if not enqueue_launch_queue(inner, f"claude-{agent_key}"):
            raise RuntimeError("launch queue write failed (mailbus watchdog)")
        # 容器内经 watchdog 异步启动，多等一会
        wait_seconds = max(wait_seconds, 45)
    else:
        result = _run_wsl_bash(inner, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(_format_start_error(result))

    for _ in range(max(1, wait_seconds)):
        if _http_ready_on_port(port) and _tmux_session_ok(agent_key):
            url = resolve_browser_url(agent_key, data_dir, browser_cfg)
            return {"agent": agent_key, "url": url, "port": port, "ready": True, "started": True}
        time.sleep(1)

    log_hint = "/tmp/claude-web/ttyd-{}.log".format(agent_key)
    raise RuntimeError(
        f"Claude ttyd 未就绪（端口 {port}）。请检查 WSL: {log_hint}；"
        f"若 localhost 不通，请用 WSL IP 打开 {url}"
    )


def _launch_url(url: str) -> None:
    ps_exe = _powershell_exe()
    if ps_exe:
        safe = url.replace("'", "''")
        _run([ps_exe, "-NoProfile", "-Command", f"Start-Process '{safe}'"], timeout=20)
        return
    cmd_helper = "/mnt/c/Windows/System32/cmd.exe"
    if os.path.isfile(cmd_helper):
        _run([cmd_helper, "/c", "start", "", url], timeout=20)
        return
    if sys.platform == "win32":
        os.startfile(url)  # type: ignore[attr-defined]
        return
    if shutil.which("xdg-open"):
        _run(["xdg-open", url], timeout=20)
        return
    raise RuntimeError(f"无法打开浏览器: {url}")


def launch_claude_browser(agent_key: str, data_dir: str) -> Dict[str, Any]:
    cfg = json_read(_config_path(data_dir), {})
    agents = cfg.get("agents") or {}
    if agent_key not in agents:
        raise ValueError(f"unknown agent: {agent_key}")
    agent_cfg = agents[agent_key]
    if agent_cfg.get("type") != "claude_code":
        raise ValueError(f"agent '{agent_key}' is not claude_code")

    browser_cfg = merge_browser_cfg(agent_key, data_dir)
    wait = int(browser_cfg.get("start_wait_seconds") or 15)
    info = ensure_claude_web(agent_key, data_dir, wait_seconds=wait)
    if not info.get("ready"):
        raise RuntimeError(f"Claude browser 未就绪: {info.get('url') or agent_key}")
    if not _running_in_mailbus_docker():
        _launch_url(info["url"])
    info["kind"] = browser_cfg.get("kind") or "claude_ttyd"
    return info


def agent_has_claude_browser(agent_cfg: dict, agent_types: dict) -> bool:
    if agent_cfg.get("type") != "claude_code":
        return False
    launch = agent_cfg.get("launch") or {}
    if launch.get("has_browser") is False:
        return False
    browser = dict(
        ((agent_types.get("launch_templates") or {}).get(launch.get("template", ""), {}) or {}).get("browser") or {}
    )
    browser.update(launch.get("browser") or {})
    kind = (browser.get("kind") or "").strip()
    return kind in ("claude_ttyd", "claude_web")
