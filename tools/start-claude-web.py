#!/usr/bin/env python3
"""WSL 内启动 Claude Code ttyd Web 终端 — start-claude-web.sh 的纯 Python 版。

用法: start-claude-web.py <agent> [web_port] [data_dir]
在 Windows 宿主经 wsl.exe 调用；已处 WSL 内则直接执行。
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _run(cmd: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _tmux_session_ok(session: str) -> bool:
    r = _run(["bash", "-lc", f"tmux has-session -t {shlex.quote(session)} 2>/dev/null"], timeout=10)
    return r.returncode == 0


def _http_ok(port: int) -> bool:
    r = _run(
        ["bash", "-lc",
         f"curl -s -o /dev/null -w '%{{http_code}}' --connect-timeout 2 --max-time 3 http://127.0.0.1:{port}/ 2>/dev/null || echo 000"],
        timeout=8,
    )
    return (r.stdout or "").strip() in ("200", "401", "403")


def _resolve_ttyd() -> str:
    ttyd = os.environ.get("TTYD_BIN", "")
    if ttyd and os.access(ttyd, os.X_OK):
        return ttyd
    r = _run(["bash", "-lc", "command -v ttyd 2>/dev/null || true"], timeout=10)
    cand = (r.stdout or "").strip()
    if cand and os.access(cand, os.X_OK):
        return cand
    for rel in (
        "docker-agents/codex-agent/bin/ttyd.x86_64",
        "tools/bin/ttyd.x86_64",
    ):
        p = os.path.join(ROOT, rel)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    _log("[claude-web] ttyd not found. Install: sudo apt install ttyd")
    _log(f"[claude-web] or use bundled: {ROOT}/docker-agents/codex-agent/bin/ttyd.x86_64")
    raise SystemExit(1)


def _auth_creds(data_dir: str, agent: str) -> tuple[str, str]:
    """浏览器入口 Basic Auth 凭据（secrets.json browser_auth.<agent>）。"""
    user = os.environ.get("TTYD_AUTH_USER", "")
    pwd = os.environ.get("TTYD_AUTH_PASS", "")
    if user and pwd:
        return user, pwd
    try:
        import json

        secrets = json.load(open(os.path.join(os.path.abspath(data_dir), "secrets.json"), encoding="utf-8"))
        c = (secrets.get("browser_auth") or {}).get(agent, {})
        return str(c.get("user", "")), str(c.get("password", ""))
    except Exception:
        return "", ""


def _stop_ttyd(port: int, pid_file: str) -> None:
    if os.path.isfile(pid_file):
        try:
            old_pid = int(open(pid_file, encoding="utf-8").read().strip() or "0")
            if old_pid:
                _run(["bash", "-lc", f"kill -0 {old_pid} 2>/dev/null && kill {old_pid} || true"], timeout=10)
                time.sleep(1)
        except (ValueError, OSError):
            pass
        try:
            os.remove(pid_file)
        except OSError:
            pass
    _run(["bash", "-lc", f"fuser -k {port}/tcp 2>/dev/null || true"], timeout=10)
    time.sleep(0.5)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        _log("Usage: start-claude-web.py <agent> [web_port] [data_dir]")
        return 1
    agent = args[0]
    port = int(args[1]) if len(args) > 1 else 9260
    data_dir = args[2] if len(args) > 2 else os.path.join(ROOT, "store")

    env_root = ROOT
    default_data = (
        os.environ.get("MAILBUS_DATA")
        or (os.path.join(os.environ["MAILBUS_ROOT"], "store") if os.environ.get("MAILBUS_ROOT") else "")
        or os.path.join(ROOT, "store")
    )
    data_dir = data_dir or default_data

    ttyd = _resolve_ttyd()
    r_tmux = _run(["bash", "-lc", "command -v tmux 2>/dev/null || true"], timeout=10)
    if not (r_tmux.stdout or "").strip():
        _log("[claude-web] tmux not installed (sudo apt install tmux)")
        return 1

    log_dir = "/tmp/claude-web"
    os.makedirs(log_dir, exist_ok=True)
    session = f"claude-{agent}"
    pid_file = os.path.join(log_dir, f"ttyd-{agent}.pid")

    if _http_ok(port) and _tmux_session_ok(session):
        _log(f"[claude-web] already listening on :{port} agent={agent} session={session}")
        return 0
    if _http_ok(port) and not _tmux_session_ok(session):
        _log(f"[claude-web] ttyd up but tmux session missing — restarting :{port}")
        _stop_ttyd(port, pid_file)

    sync_py = os.path.join(ROOT, "tools", "sync-claude-agent-context.py")
    if os.path.isfile(sync_py):
        _run([sys.executable, sync_py, agent, "--data-dir", data_dir], timeout=120)

    sys.path.insert(0, ROOT)
    from lib.adapters.frameworks.claude_launch import build_interactive_shell_inner

    start_inner = build_interactive_shell_inner(agent, data_dir)

    try:
        import json

        cfg = json.load(open(os.path.join(os.path.abspath(data_dir), "config.json"), encoding="utf-8"))
        agent_cfg = (cfg.get("agents") or {}).get(agent, {})
        agent_title = f"{agent_cfg.get('name') or agent} ({agent})"
    except Exception:
        agent_title = agent

    start_script = os.path.join(log_dir, f"start-{agent}.sh")
    with open(start_script, "w", encoding="utf-8") as fh:
        fh.write("#!/bin/bash\nset +e\nexport LANG=C.UTF-8\nexport LC_ALL=C.UTF-8\nwhile true; do\n")
        fh.write(f"  {start_inner}\n")
        fh.write('  ec=$?\n  echo\n  echo "[claude-web] shell exited ($ec). Retry in 3s — Ctrl+C to stop."\n  sleep 3\ndone\n')
    os.chmod(start_script, 0o755)

    _run(["bash", "-lc", f"tmux kill-session -t {shlex.quote(session)} 2>/dev/null || true"], timeout=10)
    time.sleep(0.5)
    _run(["bash", "-lc", f"tmux new-session -d -s {shlex.quote(session)} {shlex.quote(start_script)}"], timeout=15)

    _stop_ttyd(port, pid_file)

    user, pwd = _auth_creds(data_dir, agent)
    auth_args = []
    if user and pwd:
        auth_args = ["-c", f"{user}:{pwd}"]
    nohup_cmd = (
        f"nohup {shlex.quote(ttyd)} -p {port} -i 0.0.0.0 {shlex.join(auth_args)} -W "
        f'-t disableReuse=true -t "titleFixed={agent_title}" '
        f"tmux attach -t {shlex.quote(session)} "
        f">/tmp/claude-web/ttyd-{agent}.log 2>&1 & echo $!"
    )
    r = _run(["bash", "-lc", nohup_cmd], timeout=15)
    new_pid = (r.stdout or "").strip().splitlines()[-1] if (r.stdout or "").strip() else ""
    if new_pid.isdigit():
        with open(pid_file, "w", encoding="utf-8") as fh:
            fh.write(new_pid)

    for _ in range(25):
        if _http_ok(port) and _tmux_session_ok(session):
            _log(f"[claude-web] ready http://127.0.0.1:{port} agent={agent} session={session}")
            return 0
        time.sleep(1)

    _log(f"[claude-web] failed to start on :{port} (see {log_dir}/ttyd-{agent}.log)")
    try:
        tail = open(os.path.join(log_dir, f"ttyd-{agent}.log"), encoding="utf-8").read().splitlines()[-20:]
        for ln in tail:
            _log(ln)
    except OSError:
        pass
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
