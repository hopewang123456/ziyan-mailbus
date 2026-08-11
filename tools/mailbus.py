#!/usr/bin/env python3
"""Mailbus 统一 CLI — 跨平台替代 bat/sh 启动脚本。

用法:
  python tools/mailbus.py start              # WSL/Linux 全量启动
  python tools/mailbus.py start --windows    # Windows 入口（唤醒 WSL + 开浏览器）
  python tools/mailbus.py stop
  python tools/mailbus.py recover quick|full|health
  python tools/mailbus.py launch lingyun browser
  python tools/mailbus.py proxy setup|ollama start|stop|status
  python tools/mailbus.py watchdog restart
  python tools/mailbus.py smoke
  python tools/mailbus.py portproxy
  python tools/mailbus.py claude ensure|stop
  python tools/mailbus.py codex apply
  python tools/mailbus.py openclaw fix
  python tools/mailbus.py doctor
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.infra.env_bootstrap import load_mailbus_env, mailbus_paths  # noqa: E402
from lib.adapters.plane.platform_runner import (  # noqa: E402
    detect_platform,
    docker_ready,
    init_stdio,
    mailbus_py_in_wsl,
    probe_http,
    run_wsl,
    wake_wsl,
)
from lib.adapters.plane.lifecycle import (  # noqa: E402
    ensure_ollama_wsl_proxy,
    restart_watchdog,
    run_watchdog_foreground,
    setup_container_proxy,
    start_from_windows,
    start_team,
    stop_from_windows,
    stop_team,
    wsl_recover,
)
from lib.adapters.plane.post_start import (  # noqa: E402
    apply_codex_ui,
    ensure_claude_agents,
    fix_openclaw_gateways,
    fix_portproxy,
    smoke_test,
    stop_claude_agents,
)


def _scan_shell_scripts() -> list[str]:
    exts = {".sh", ".bat", ".ps1", ".cmd"}
    skip_dirs = {".git", ".test-venv", "node_modules", "__pycache__", "vendor"}
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for name in filenames:
            if os.path.splitext(name)[1].lower() in exts:
                rel = os.path.relpath(os.path.join(dirpath, name), ROOT)
                found.append(rel.replace("\\", "/"))
    return sorted(found)


def cmd_start(args: argparse.Namespace) -> int:
    fast = bool(getattr(args, "fast", False))
    if args.windows or detect_platform() == "win32":
        return start_from_windows(open_browser=args.open_browser, fast=fast)
    return start_team(skip_lock=args.no_lock, fast=fast)


def cmd_stop(_args: argparse.Namespace) -> int:
    if detect_platform() == "win32":
        return stop_from_windows()
    return stop_team()


def cmd_recover(args: argparse.Namespace) -> int:
    if args.action == "health":
        paths = mailbus_paths()
        # / 依赖 docs 静态页；API 就绪以 /api/status 为准
        url = f"http://127.0.0.1:{paths['api_port']}/api/status"
        ok = probe_http(url)
        print(f"[recover] platform={detect_platform()} mailbus={url} -> {'OK' if ok else 'DOWN'}")
        rc = 0 if ok else 1
        if detect_platform() == "win32":
            win_ok = probe_http(url)
            print(f"[recover] Windows localhost -> {'OK' if win_ok else 'DOWN'}")
            if ok and not win_ok:
                rc = 2
        return rc

    if detect_platform() == "win32" and args.action in ("quick", "full"):
        if not wake_wsl():
            return 1
        parts = ["recover", args.action]
        if args.no_scan:
            parts.append("--no-scan")
        return run_wsl(mailbus_py_in_wsl(parts), timeout=3600)

    if args.action == "full":
        return wsl_recover(full=True, scan=not args.no_scan)
    return wsl_recover(full=False, scan=not args.no_scan)


def cmd_launch(args: argparse.Namespace) -> int:
    from tools.ops.launch_agent import launch_agent

    return launch_agent(args.agent, args.mode, args.data_dir or mailbus_paths()["data_dir"])


def cmd_proxy(args: argparse.Namespace) -> int:
    if args.action == "setup":
        setup_container_proxy()
        return 0
    return ensure_ollama_wsl_proxy(args.action)


def cmd_watchdog(args: argparse.Namespace) -> int:
    if args.action == "run":
        return run_watchdog_foreground()
    return restart_watchdog()


def cmd_doctor(_args: argparse.Namespace) -> int:
    """检测 Docker（含 WSL）、路径、AgentMemory、恢复完整性。"""
    from lib.adapters.ops.doctor_checks import doctor_exit_code, format_doctor_text, run_doctor_checks

    report = run_doctor_checks()
    print(format_doctor_text(report))
    return doctor_exit_code(report)


def cmd_smoke(args: argparse.Namespace) -> int:
    return smoke_test(wait_sec=args.wait, am_persist=args.am_persist)


def cmd_portproxy(_args: argparse.Namespace) -> int:
    # Native Linux/macOS: no-op inside fix_portproxy. Win32/WSL: refresh portproxy when script exists.
    return fix_portproxy()


def cmd_claude(args: argparse.Namespace) -> int:
    if args.action == "ensure":
        if detect_platform() == "win32":
            return run_wsl(mailbus_py_in_wsl(["claude", "ensure"]), timeout=600)
        return ensure_claude_agents()
    if detect_platform() == "win32":
        return run_wsl(mailbus_py_in_wsl(["claude", "stop"]), timeout=120)
    return stop_claude_agents()


def cmd_codex(_args: argparse.Namespace) -> int:
    if detect_platform() == "win32":
        return run_wsl(mailbus_py_in_wsl(["codex", "apply"]), timeout=900)
    return apply_codex_ui()


def cmd_openclaw(_args: argparse.Namespace) -> int:
    if detect_platform() == "win32":
        return run_wsl(mailbus_py_in_wsl(["openclaw", "fix"]), timeout=600)
    return fix_openclaw_gateways()


def cmd_compose(args: argparse.Namespace) -> int:
    if args.action != "sync":
        return 1
    gen = os.path.join(ROOT, "tools", "generate-compose-volumes.py")
    r1 = subprocess.run([sys.executable, gen, "--emit"], cwd=ROOT)
    if r1.returncode != 0:
        return r1.returncode
    return subprocess.run([sys.executable, gen, "--check"], cwd=ROOT).returncode


def cmd_migrate(args: argparse.Namespace) -> int:
    from lib.adapters.ops.migrate_ops import cmd_migrate_export, cmd_migrate_import, cmd_migrate_plan

    if args.action == "plan":
        return cmd_migrate_plan(args)
    if args.action == "export":
        return cmd_migrate_export(args)
    if args.action == "import":
        return cmd_migrate_import(args)
    return 1


def cmd_scripts(args: argparse.Namespace) -> int:
    scripts = _scan_shell_scripts()
    if args.action == "count":
        print(len(scripts))
        return 0
    docker = [s for s in scripts if s.startswith("docker-agents/")]
    tools = [s for s in scripts if s.startswith("tools/")]
    other = [s for s in scripts if s not in docker and s not in tools]
    print(f"Total shell scripts under mailbus-core: {len(scripts)}")
    print(f"  docker-agents/: {len(docker)} (容器 entrypoint 建议保留 bash)")
    print(f"  tools/:         {len(tools)}")
    print(f"  other:          {len(other)}")
    if args.action == "list":
        for s in scripts:
            print(s)
    return 0


def cmd_docker(args: argparse.Namespace) -> int:
    from lib.application.ops.docker_helpers import (
        ensure_ollama_cli,
        restart_mailbus_container,
        start_n8n,
        up_comfyui_gpu,
    )

    if args.action == "restart-mailbus":
        return restart_mailbus_container()
    if args.action == "start-n8n":
        return start_n8n()
    if args.action == "up-comfyui":
        return up_comfyui_gpu()
    if args.action == "ensure-ollama":
        return ensure_ollama_cli(
            data_dir=args.data_dir or "",
            no_pull=not args.pull,
            wait_seconds=args.wait_seconds,
        )
    return 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="mailbus", description="Mailbus unified cross-platform CLI")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("start", help="start ziyan AI team")
    p.add_argument("--windows", action="store_true", help="Windows entry: wake WSL + portproxy + browser")
    p.add_argument("--open-browser", action="store_true", help="open agent URLs in browser (Windows)")
    p.add_argument("--no-lock", action="store_true", help="skip start-team flock lock")
    p.add_argument("--fast", action="store_true", help="skip smoke / Ollama ensure (faster daily start)")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("stop", help="stop all team containers")
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser("recover", help="light/full stack recovery")
    p.add_argument("action", choices=("health", "quick", "full"))
    p.add_argument("--no-scan", action="store_true", help="skip post-recover bus scan")
    p.set_defaults(func=cmd_recover)

    p = sub.add_parser("launch", help="launch single agent (browser/cli/desktop)")
    p.add_argument("agent")
    p.add_argument("mode", nargs="?", default="browser", choices=("browser", "cli", "desktop"))
    p.add_argument("--data-dir", default="")
    p.set_defaults(func=cmd_launch)

    p = sub.add_parser("proxy", help="container proxy / ollama-wsl-proxy")
    p.add_argument("action", choices=("setup", "start", "stop", "restart", "status"))
    p.set_defaults(func=cmd_proxy)

    p = sub.add_parser("watchdog", help="mailbus launch watchdog")
    p.add_argument("action", nargs="?", default="restart", choices=("restart", "run"))
    p.set_defaults(func=cmd_watchdog)

    p = sub.add_parser("doctor", help="check Docker, paths, ports, AgentMemory")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("smoke", help="post-start smoke test")
    p.add_argument("--wait", type=int, default=None, help="seconds before checks (default SMOKE_WAIT_SEC)")
    p.add_argument("--am-persist", action="store_true", help="run AgentMemory persistence probe")
    p.set_defaults(func=cmd_smoke)

    p = sub.add_parser("portproxy", help="refresh Windows localhost port forwarding")
    p.set_defaults(func=cmd_portproxy)

    p = sub.add_parser("claude", help="ensure/stop Claude ttyd (lingyun/lingyan)")
    p.add_argument("action", choices=("ensure", "stop"))
    p.set_defaults(func=cmd_claude)

    p = sub.add_parser("codex", help="Codex container post-start")
    p.add_argument("action", choices=("apply",))
    p.set_defaults(func=cmd_codex)

    p = sub.add_parser("openclaw", help="fix OpenClaw gateways (xiaoqi/yige)")
    p.add_argument("action", choices=("fix",))
    p.set_defaults(func=cmd_openclaw)

    p = sub.add_parser("compose", help="sync docker-compose override from transport registry")
    p.add_argument("action", choices=("sync",))
    p.set_defaults(func=cmd_compose)

    mig = sub.add_parser("migrate", help="export/import/plan directory migration")
    mig_sub = mig.add_subparsers(dest="action", required=True)
    mp = mig_sub.add_parser("plan", help="show manifest vs current paths")
    mp.set_defaults(func=cmd_migrate)
    me = mig_sub.add_parser("export", help="tar.gz bundle from install prefix")
    me.add_argument("--prefix", default="")
    me.add_argument("--output", default="mailbus-bundle.tar.gz")
    me.add_argument("--no-infra", action="store_true")
    me.set_defaults(func=cmd_migrate)
    mi = mig_sub.add_parser("import", help="unpack bundle and run post steps")
    mi.add_argument("bundle")
    mi.add_argument("--prefix", required=True)
    mi.add_argument("--dry-run", action="store_true")
    mi.add_argument("--skip-post", action="store_true")
    mi.set_defaults(func=cmd_migrate)

    p = sub.add_parser("scripts", help="inventory remaining shell scripts")
    p.add_argument("action", choices=("list", "count"), default="count", nargs="?")
    p.set_defaults(func=cmd_scripts)

    dock = sub.add_parser("docker", help="cross-platform docker helpers (replaces *.ps1 ops)")
    dock_sub = dock.add_subparsers(dest="action", required=True)
    p = dock_sub.add_parser("restart-mailbus", help="docker compose restart mailbus")
    p.set_defaults(func=cmd_docker)
    p = dock_sub.add_parser("start-n8n", help="up n8n compose stack")
    p.set_defaults(func=cmd_docker)
    p = dock_sub.add_parser("up-comfyui", help="up ComfyUI GPU compose")
    p.set_defaults(func=cmd_docker)
    p = dock_sub.add_parser("ensure-ollama", help="run tools/ensure-ollama.py")
    p.add_argument("--data-dir", default="")
    p.add_argument("--pull", action="store_true", help="allow model pull")
    p.add_argument("--wait-seconds", type=int, default=90)
    p.set_defaults(func=cmd_docker)

    return ap


def main(argv: list[str] | None = None) -> int:
    init_stdio()
    load_mailbus_env()
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
