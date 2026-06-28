#!/usr/bin/env python3
"""mailbus live 验收 pre-flight：容器/API/agent/iteration 状态检查。"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.constants import DEFAULT_DATA_DIR
from lib.tracker import TaskStatus, TaskTracker
from lib.utils import json_read, resolve_paths

PIPELINE_AGENTS = (
    "lingzhao", "lingxi", "xiaoqi", "lingxiao", "dali",
    "lingjin", "lingjian", "lingyan", "lingxun", "yige",
)


def _get(url: str, timeout: float = 5.0) -> dict:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _docker_ps() -> set[str]:
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=15, check=False,
        )
        if out.returncode != 0:
            return set()
        return {ln.strip() for ln in out.stdout.splitlines() if ln.strip()}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return set()


def check_docker_paths() -> tuple[bool, str]:
    """Windows：宿主机 docker 与 WSL docker 双路径探测。"""
    host = shutil.which("docker")
    wsl = None
    if sys.platform == "win32":
        try:
            r = subprocess.run(
                ["wsl", "-e", "bash", "-lc", "command -v docker"],
                capture_output=True, text=True, timeout=15, check=False,
            )
            if r.returncode == 0 and (r.stdout or "").strip():
                wsl = (r.stdout or "").strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    if host:
        return True, f"host docker={host}"
    if wsl:
        return True, f"wsl docker={wsl}"
    return False, "docker not found on host or WSL"


def check_bus_serve(base: str) -> tuple[bool, str]:
    """bus serve / scheduler scan 须启用。"""
    try:
        data = _get(f"{base.rstrip('/')}/api/system/scheduler")
        jobs = data.get("jobs") or []
        scan = next((j for j in jobs if j.get("id") == "scan"), None)
        if not scan:
            return False, "scan job missing"
        if not scan.get("enabled"):
            return False, "scan job disabled — 需单实例 mailbus serve"
        return True, "scan enabled"
    except Exception as exc:
        return False, str(exc)


def check_codex_sandbox(data_dir: str) -> tuple[bool, str]:
    """灵鉴 Codex sandbox 探测（WSL 无 userns 时 WARN）。"""
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    lingjian = (cfg.get("agents") or {}).get("lingjian") or {}
    if lingjian.get("type") != "codex":
        return True, "lingjian not codex (skip)"
    sandbox = (lingjian.get("codex") or {}).get("sandbox") or lingjian.get("sandbox") or ""
    if sandbox in ("danger-full-access", "full-access"):
        return True, f"sandbox={sandbox}"
    try:
        r = subprocess.run(
            ["codex", "exec", "--sandbox", "read-only", "echo", "ok"],
            capture_output=True, text=True, timeout=45, check=False,
        )
        if r.returncode == 0:
            return True, "codex sandbox read-only ok"
        err = (r.stderr or r.stdout or "")[:120]
        if "bwrap" in err.lower() or "userns" in err.lower():
            return False, f"codex bwrap/userns fail: {err}"
        return False, err or f"exit {r.returncode}"
    except FileNotFoundError:
        return True, "codex CLI not in PATH (skip)"
    except subprocess.TimeoutExpired:
        return False, "codex sandbox probe timeout"


def check_audit_queue(data_dir: str) -> tuple[bool, str]:
    """主 pipeline running 时 audit 队列长度（争槽预警）。"""
    from lib.pipeline_task import primary_pipeline_assignee

    assignee = primary_pipeline_assignee(data_dir)
    if not assignee:
        return True, "no primary pipeline"
    audit_dir = os.path.join(data_dir, "audit-queue")
    pending = 0
    if os.path.isdir(audit_dir):
        for fn in os.listdir(audit_dir):
            if not fn.endswith(".json"):
                continue
            item = json_read(os.path.join(audit_dir, fn), {})
            if (item.get("status") or "").lower() in ("pending", "queued", ""):
                pending += 1
    if pending > 5:
        return False, f"audit queue backlog={pending} while primary={assignee}"
    return True, f"primary={assignee} audit_pending={pending}"


def check_claude_code(data_dir: str) -> tuple[bool, str]:
    """claude_code agent 可达性。"""
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    agents = cfg.get("agents") or {}
    claude_agents = [n for n, a in agents.items() if (a or {}).get("type") == "claude_code"]
    if not claude_agents:
        return True, "no claude_code agents"
    try:
        from lib.claude_launch import load_mailbus_claude, resolve_claude_plat_cfg, resolve_claude_bin

        global_cfg = load_mailbus_claude(data_dir)
        plat, plat_cfg = resolve_claude_plat_cfg(global_cfg)
        if plat == "windows":
            from lib.claude_launch import resolve_windows_claude_bin
            bin_path = resolve_windows_claude_bin(plat_cfg)
        else:
            bin_path = resolve_claude_bin(plat_cfg) or "claude"
        if shutil.which(bin_path) or os.path.isfile(bin_path):
            return True, f"claude ok ({plat}) {bin_path}"
        return False, f"claude not found: {bin_path}"
    except Exception as exc:
        return False, str(exc)


def check_api(base: str) -> tuple[bool, str]:
    try:
        data = _get(f"{base.rstrip('/')}/api/status")
        return "agents" in data or "project" in data, json.dumps(
            {"agents": data.get("agents"), "unread": data.get("unread_messages")},
            ensure_ascii=False,
        )[:200]
    except Exception as exc:
        return False, str(exc)


def check_scheduler(base: str) -> tuple[bool, str]:
    try:
        data = _get(f"{base.rstrip('/')}/api/system/scheduler")
        jobs = data.get("jobs") or []
        scan = next((j for j in jobs if j.get("id") == "scan"), None)
        if not scan:
            return False, "scan job missing"
        return True, f"jobs={len(jobs)} scan_enabled={scan.get('enabled')}"
    except Exception as exc:
        return False, str(exc)


def check_iteration(data_dir: str, *, allow_primary: str = "") -> tuple[bool, str]:
    state = json_read(os.path.join(data_dir, "iterations", "iteration-state.json"), {})
    primary = state.get("primary_task_id") or ""
    if not primary:
        return True, "no primary_task_id"
    tr = TaskTracker(data_dir)
    t = tr.get(primary) or {}
    st = t.get("status", "")
    if allow_primary and primary == allow_primary and st in (TaskStatus.RUNNING, TaskStatus.PENDING):
        return True, f"primary={primary} status={st} (live acceptance)"
    if st in (TaskStatus.RUNNING, TaskStatus.PENDING) and primary != allow_primary:
        return False, f"blocking primary {primary} status={st}"
    return True, f"primary={primary} status={st}"


def check_agents(data_dir: str, names: tuple[str, ...]) -> tuple[bool, list[str]]:
    paths = resolve_paths(data_dir)
    issues = []
    for name in names:
        inbox = os.path.join(paths["inbox"], name, "inbox.json")
        if not os.path.isfile(inbox):
            issues.append(f"{name}: no inbox")
    return len(issues) == 0, issues


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default=os.environ.get("MAILBUS_DATA", DEFAULT_DATA_DIR))
    p.add_argument("--api", default=os.environ.get("MAILBUS_API", "http://127.0.0.1:9814"))
    p.add_argument("--task-id", default="", help="可选：检查指定 pipeline 任务")
    args = p.parse_args()
    data_dir = os.path.abspath(args.data_dir)
    blockers: list[str] = []

    ok, detail = check_api(args.api)
    print(f"api: {'OK' if ok else 'FAIL'} — {detail}")
    if not ok:
        blockers.append("api")

    ok, detail = check_bus_serve(args.api)
    print(f"bus_serve: {'OK' if ok else 'BLOCK'} — {detail}")
    if not ok:
        blockers.append("bus_serve")

    ok, detail = check_scheduler(args.api)
    print(f"scheduler: {'OK' if ok else 'WARN'} — {detail}")

    ok, detail = check_iteration(data_dir, allow_primary=args.task_id)
    print(f"iteration: {'OK' if ok else 'BLOCK'} — {detail}")
    if not ok:
        blockers.append("iteration")

    ok, detail = check_docker_paths()
    print(f"docker_paths: {'OK' if ok else 'WARN'} — {detail}")

    ok, detail = check_codex_sandbox(data_dir)
    print(f"codex_sandbox: {'OK' if ok else 'BLOCK'} — {detail}")
    if not ok:
        blockers.append("codex_sandbox")

    ok, detail = check_claude_code(data_dir)
    print(f"claude_code: {'OK' if ok else 'BLOCK'} — {detail}")
    if not ok:
        blockers.append("claude_code")

    ok, detail = check_audit_queue(data_dir)
    print(f"audit_queue: {'OK' if ok else 'WARN'} — {detail}")

    containers = _docker_ps()
    if containers:
        mailbus_up = any("mailbus" in c for c in containers)
        print(f"docker: {len(containers)} containers mailbus={'up' if mailbus_up else 'missing'}")
        if not mailbus_up:
            blockers.append("docker-mailbus")
    else:
        print("docker: unavailable (skip)")

    ok, issues = check_agents(data_dir, PIPELINE_AGENTS)
    print(f"agents: {'OK' if ok else 'FAIL'} — {len(PIPELINE_AGENTS)} checked")
    for issue in issues:
        print(f"  - {issue}")
        blockers.append(issue)

    if args.task_id:
        tr = TaskTracker(data_dir)
        t = tr.get(args.task_id)
        if not t:
            print(f"task {args.task_id}: NOT_FOUND")
            blockers.append("task-missing")
        else:
            chain = t.get("chain") or []
            step = chain[-1] if chain else {}
            print(
                f"task {args.task_id}: status={t.get('status')} "
                f"step={step.get('step')} assignee={step.get('to_person') or t.get('assignee')}"
            )

    if blockers:
        print(f"PREFLIGHT: BLOCKED ({len(blockers)} issues)")
        return 1
    print("PREFLIGHT: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
