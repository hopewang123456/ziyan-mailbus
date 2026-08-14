"""Hermes dashboard 管理 — 纯 Python 启动/健康检查/守护。

遵循 Mailbus 架构原则：agent 访问应通过 Python 模块，而非裸 shell 命令。

入口（容器内）：
    python3.12 -m lib.adapters.frameworks.hermes_dashboard start-all
    python3.12 -m lib.adapters.frameworks.hermes_dashboard ensure [profile] [port]

外部 watchdog（宿主机 docker exec）：
    docker exec <container> python3.12 -m lib.adapters.frameworks.hermes_dashboard ensure <profile> <port>
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional

# ── 编制内全部 dashboard（与 entrypoint.sh / ORGANIZATION.md 一致）──
# 从 store/config.json 的 hermes_profile 类型 agents 读取，demo 名作为 fallback
_DEMO_DASHBOARDS: list[tuple[str, int]] = [
    ("agent-a", 9120),
    ("agent-b", 9121),
    ("agent-c", 9122),
]


def _data_dir() -> str:
    return os.environ.get("MAILBUS_DATA_DIR") or os.environ.get("DATA_DIR") or str(
        Path(__file__).resolve().parents[3] / "store"
    )


def dashboards() -> list[tuple[str, int]]:
    """读取编制内 dashboard：config.json hermes_profile · port / launch.browser / launch-ports。"""
    import json as _json

    cfg_path = Path(_data_dir()) / "config.json"
    items: list[tuple[str, int]] = []
    try:
        if cfg_path.is_file():
            cfg = _json.loads(cfg_path.read_text(encoding="utf-8"))
            agents = cfg.get("agents") or {}
            from lib.adapters.config.launch_ports import resolve_port

            for aid, ac in agents.items():
                if not isinstance(ac, dict):
                    continue
                if (ac.get("type") or "").strip() != "hermes_profile":
                    continue
                launch = ac.get("launch") or {}
                browser = dict(launch.get("browser") or {})
                port = resolve_port(aid, ac, browser, group="hermes_dashboard")
                if port in (None, ""):
                    port = ac.get("port")
                if port in (None, ""):
                    continue
                items.append((aid, int(port)))
    except Exception:
        pass
    if items:
        return items
    return list(_DEMO_DASHBOARDS)

PYTHON_BIN = "python3.12"
HERMES_MODULE = "hermes_cli.main"

# dashboard 启动通用参数
# --insecure：跳过非 loopback 绑定(0.0.0.0)时的 OAuth auth gate（容器内未装
# DashboardAuthProvider 插件）。鉴权改为 mailbus 注入固定 HERMES_DASHBOARD_SESSION_TOKEN
# （跨重启不变，见 _session_token()）——loopback/--insecure 模式下 SPA 从 HTML 注入该
# token 并经 X-Hermes-Session-Token 回传，实现持久免密。
DASH_ARGS = [
    "dashboard",
    "--host", "0.0.0.0",
    "--insecure",
    "--skip-build",
    "--isolated",
]

LOG_DIR = "/tmp"


def _session_token() -> str:
    """固定 Hermes dashboard session token（跨重启不变，存 store/secrets.json）。

    Hermes 每次启动默认随机 mint session token 导致浏览器反复要 token；
    mailbus 生成固定值持久化并注入 env，浏览器第一次输入后记住免密。
    """
    env_token = os.environ.get("HERMES_DASHBOARD_SESSION_TOKEN", "").strip()
    if env_token:
        return env_token
    try:
        from lib.adapters.config.token_store import ensure_browser_credentials

        cred = ensure_browser_credentials(_data_dir(), "hermes", mode="token")
        token = (cred.get("token") or "").strip()
        if token:
            return token
    except Exception:
        pass
    import secrets as _secrets

    return _secrets.token_urlsafe(24)


# ── 健康检查 ──────────────────────────────────────────────────────

def check_dashboard(port: int, timeout: float = 3.0) -> Optional[int]:
    """HTTP 健康检查，返回状态码或 None（不可达）。"""
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/", method="GET"
        )
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status
    except Exception:
        return None


# ── 启动单个 dashboard ─────────────────────────────────────────────

def start_dashboard(profile: str, port: int) -> bool:
    """启动单个 profile 的 dashboard 进程（daemon）。返回是否成功就绪。"""
    log_path = Path(LOG_DIR) / f"hermes-dash-{profile}.log"

    # 先检查是否已在运行
    status = check_dashboard(port)
    if status is not None and status in (200, 301, 302):
        print(f"  {profile} ({port}) already up (HTTP {status})")
        return True

    # 构造命令：python3.12 -m hermes_cli.main -p <profile> dashboard --host 0.0.0.0 ...
    # --open-profile 让浏览器打开时 UI 自动选中该 profile，无需手动切换
    cmd = [
        PYTHON_BIN, "-m", HERMES_MODULE,
        "-p", profile,
        *DASH_ARGS,
        "--open-profile", profile,
        "--port", str(port),
    ]

    print(f"  {profile} ({port}) starting...")
    env = os.environ.copy()
    env["HERMES_DASHBOARD_SESSION_TOKEN"] = _session_token()
    with open(log_path, "wb") as log_file:
        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,  # daemonize
            env=env,
        )
    pid = proc.pid
    print(f"  {profile} ({port}) starting pid={pid}")

    # 等待就绪（最多 30s）
    for _ in range(15):
        time.sleep(2)
        status = check_dashboard(port)
        if status is not None and status in (200, 301, 302):
            print(f"  {profile} ({port}) ready (HTTP {status})")
            return True

    print(f"  WARNING: {profile} ({port}) not ready — see {log_path}")
    _tail_log(log_path)
    return False


def _tail_log(log_path: Path, lines: int = 3) -> None:
    """打印日志尾部用于故障排查。"""
    try:
        if log_path.is_file():
            content = log_path.read_text(errors="replace")
            tail = "\n".join(content.strip().splitlines()[-lines:])
            if tail:
                print(f"  log tail ({log_path}):\n{tail}")
    except Exception:
        pass


# ── 守护模式（ensure）─────────────────────────────────────────────

def ensure_dashboard(profile: str, port: int) -> bool:
    """确保 dashboard 就绪；未运行则启动。返回是否成功。"""
    status = check_dashboard(port)
    if status is not None and status in (200, 301, 302):
        print(f"  [{profile}:{port}] OK (HTTP {status})")
        return True
    print(f"  [{profile}:{port}] not responding (was HTTP {status or 'unreachable'}), starting...")
    return start_dashboard(profile, port)


def ensure_all() -> int:
    """确保全部 dashboard 就绪。返回失败数。"""
    failures = 0
    for profile, port in dashboards():
        try:
            if not ensure_dashboard(profile, port):
                failures += 1
        except Exception as e:
            print(f"  [{profile}:{port}] ERROR: {e}")
            failures += 1
    if failures:
        print(f"\n[hermes-dashboard] {failures} dashboard(s) failed")
    else:
        print("[hermes-dashboard] all dashboards OK")
    return failures


def start_all() -> int:
    """启动全部 dashboard。返回失败数。"""
    failures = 0
    for profile, port in dashboards():
        try:
            if not start_dashboard(profile, port):
                failures += 1
        except Exception as e:
            print(f"  [{profile}:{port}] ERROR: {e}")
            failures += 1
    if failures:
        print(f"\n[hermes-dashboard] {failures} dashboard(s) failed")
    else:
        print("[hermes-dashboard] all dashboards launched")
    return failures


# ── CLI ───────────────────────────────────────────────────────────

def main() -> None:
    usage = (
        "Usage:\n"
        "  hermes_dashboard start-all               # 启动全部（容器 entrypoint）\n"
        "  hermes_dashboard ensure-all               # 守护全部（watchdog）\n"
        "  hermes_dashboard ensure <profile> <port>  # 守护单个（外部 docker exec）\n"
    )

    args = sys.argv[1:]
    if not args:
        print(usage, file=sys.stderr)
        sys.exit(2)

    cmd = args[0]

    if cmd == "start-all":
        sys.exit(start_all())

    elif cmd == "ensure-all":
        sys.exit(ensure_all())

    elif cmd == "ensure":
        if len(args) < 3:
            print("Missing profile or port", file=sys.stderr)
            print(usage, file=sys.stderr)
            sys.exit(2)
        profile = args[1]
        try:
            port = int(args[2])
        except ValueError:
            print(f"Invalid port: {args[2]}", file=sys.stderr)
            sys.exit(2)
        ok = ensure_dashboard(profile, port)
        sys.exit(0 if ok else 1)

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print(usage, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
