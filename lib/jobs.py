"""mailbus 内置调度任务 — 供 scheduler 与 CLI 共用。"""

from __future__ import annotations

import io
import os
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone, timedelta
from typing import Optional

from .models import MsgType, Priority
from .utils import build_message, json_read, json_write, resolve_paths, _now_iso

TZ_CN = timezone(timedelta(hours=8))


def _mail_root(data_dir: str) -> str:
    return os.path.dirname(os.path.abspath(data_dir))


def run_scan(data_dir: str, config: dict, *, quiet: bool = False) -> int:
    """执行一轮 bus scan（与 cmd_scan 相同逻辑）。"""
    from .commands import run_scan_once
    return run_scan_once(data_dir, config, quiet=quiet)


def run_memory_bridge(data_dir: str, limit: int = 20) -> int:
    root = _mail_root(data_dir)
    script = os.path.join(root, "mailbus-memory-bridge.py")
    if not os.path.isfile(script):
        return 0
    env = os.environ.copy()
    if "AGENTMEMORY_URL" not in env:
        env["AGENTMEMORY_URL"] = "http://127.0.0.1:3111"
    if os.path.exists("/.dockerenv") and "TEAM_MEMORY_DB" not in env:
        env["TEAM_MEMORY_DB"] = "/hermes/shared-memory/team-memory.db"
    try:
        r = subprocess.run(
            [sys.executable, script, "--data-dir", data_dir, "--limit", str(min(limit, 10))],
            cwd=root, env=env, capture_output=True, text=True, timeout=90,
        )
        if r.stdout:
            print(r.stdout.rstrip())
        if r.returncode != 0 and r.stderr:
            print(r.stderr.rstrip(), file=sys.stderr)
        return r.returncode
    except subprocess.TimeoutExpired:
        print("[memory-bridge] timeout", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"[memory-bridge] error: {exc}", file=sys.stderr)
        return 1


def _agentmemory_watchdog_state_path(data_dir: str) -> str:
    system_dir = os.path.join(data_dir, "system")
    os.makedirs(system_dir, exist_ok=True)
    return os.path.join(system_dir, "agentmemory-watchdog.json")


def _docker_sock_available() -> bool:
    return os.path.exists("/var/run/docker.sock")


def _resolve_am_containers() -> list[str]:
    """解析 iii-engine / agentmemory 容器名。"""
    ordered: list[str] = []
    for suffix in ("iii-engine", "agentmemory"):
        env_key = f"AGENTMEMORY_{suffix.upper().replace('-', '_')}_CONTAINER"
        explicit = os.environ.get(env_key, "").strip()
        if explicit:
            ordered.append(explicit)
            continue
        try:
            r = subprocess.run(
                ["docker", "ps", "-a", "--filter", f"name={suffix}", "--format", "{{.Names}}"],
                capture_output=True, text=True, timeout=15,
            )
            for line in (r.stdout or "").splitlines():
                line = line.strip()
                if line and suffix in line and line not in ordered:
                    ordered.append(line)
                    break
        except Exception:
            pass
    return ordered


def _restart_agentmemory_containers() -> tuple[bool, str]:
    compose_dir = os.environ.get(
        "MAILBUS_COMPOSE_DIR",
        "/mailbus/docker-agents" if os.path.exists("/mailbus/docker-agents") else "",
    )
    if compose_dir and os.path.isfile(os.path.join(compose_dir, "docker-compose.yml")):
        try:
            r = subprocess.run(
                ["docker", "compose", "-f", os.path.join(compose_dir, "docker-compose.yml"),
                 "restart", "iii-engine", "agentmemory"],
                capture_output=True, text=True, timeout=120,
            )
            if r.returncode == 0:
                return True, "docker compose restart"
            detail = (r.stderr or r.stdout or "").strip()[:200]
        except FileNotFoundError:
            detail = "docker compose not found"
        except subprocess.TimeoutExpired:
            return False, "docker compose restart timeout"
        except Exception as exc:
            detail = str(exc)[:200]
    else:
        detail = "compose dir missing"

    containers = _resolve_am_containers()
    if not containers:
        return False, detail or "no containers found"
    try:
        r = subprocess.run(
            ["docker", "restart", *containers],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode == 0:
            return True, f"docker restart {' '.join(containers)}"
        return False, (r.stderr or r.stdout or detail)[:200]
    except Exception as exc:
        return False, str(exc)[:200]


def run_agentmemory_watchdog(data_dir: str) -> int:
    """AgentMemory 健康看门狗：连续失败则 docker 重启。"""
    from .heartbeat import check_agentmemory
    from .memory_bridge import bridge_agentmemory_enabled

    if not bridge_agentmemory_enabled():
        return 0

    state_path = _agentmemory_watchdog_state_path(data_dir)
    state = json_read(state_path, {})
    health = check_agentmemory()
    status = health.get("status", "unreachable")
    now = _now_iso()

    bad = status in ("unreachable", "degraded")
    fail_streak = int(state.get("fail_streak", 0))
    if bad:
        fail_streak += 1
    else:
        fail_streak = 0

    state.update({
        "last_check": now,
        "last_status": status,
        "fail_streak": fail_streak,
        "detail": health.get("detail", ""),
    })

    restarted = False
    restart_detail = ""
    if bad and fail_streak >= 2 and _docker_sock_available():
        ok, restart_detail = _restart_agentmemory_containers()
        state["last_restart_attempt"] = now
        state["last_restart_ok"] = ok
        state["last_restart_detail"] = restart_detail
        restarted = ok
        if ok:
            fail_streak = 0
            state["fail_streak"] = 0
            # 等待 health 恢复
            import time
            from .alerter import push_alert
            for _ in range(60):
                time.sleep(1)
                h = check_agentmemory()
                if h.get("status") == "healthy":
                    push_alert(data_dir, "agentmemory_up", "info", "system",
                               "AgentMemory 看门狗重启后已恢复")
                    break
            else:
                push_alert(data_dir, "agentmemory_down", "critical", "system",
                           f"AgentMemory 看门狗重启后仍不可用: {restart_detail}")
        else:
            from .alerter import push_alert
            push_alert(data_dir, "agentmemory_down", "critical", "system",
                       f"AgentMemory 看门狗重启失败: {restart_detail}")

    state["fail_streak"] = fail_streak
    json_write(state_path, state)
    status_path = os.path.join(os.path.dirname(state_path), "agentmemory-status.json")
    json_write(status_path, {
        "last_check": now,
        "status": status,
        "healthy": not bad,
        "fail_streak": fail_streak,
        "detail": health.get("detail", ""),
    })

    if restarted:
        print(f"[am-watchdog] restarted ({restart_detail})")
    elif bad:
        print(f"[am-watchdog] unhealthy streak={fail_streak} ({status})")
    else:
        print(f"[am-watchdog] ok ({status})")
    return 0 if not bad or restarted else 1


def run_log_rotate(data_dir: str) -> int:
    root = _mail_root(data_dir)
    script = os.path.join(root, "mailbus-log-rotate.py")
    if not os.path.isfile(script):
        return 0
    try:
        r = subprocess.run(
            [sys.executable, script],
            cwd=root, capture_output=True, text=True, timeout=120,
        )
        if r.stdout:
            print(r.stdout.rstrip())
        return r.returncode
    except Exception as exc:
        print(f"[log-rotate] error: {exc}", file=sys.stderr)
        return 1


def _append_inbox_task(data_dir: str, to: str, content: str, *, priority: str = "normal") -> None:
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{to}/inbox.json"
    from .models import Inbox
    from .utils import json_read

    inbox_data = json_read(inbox_file, {})
    inbox = Inbox.from_dict(inbox_data) if inbox_data else Inbox(agent=to)
    msg = build_message("mailbus", to, content, MsgType.TASK, Priority.URGENT if priority == "urgent" else Priority.NORMAL)
    inbox.messages.append(msg)
    inbox.has_unread = True
    json_write(inbox_file, inbox.to_dict())


def _append_inbox_notice(
    data_dir: str,
    to: str,
    content: str,
    *,
    msg_id: str = "",
    priority: str = "normal",
    no_llm: bool = True,
) -> None:
    """写入 notice（默认零 LLM：mailbus scan 自动 digest，不 spawn Hermes）。"""
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{to}/inbox.json"
    from .models import Inbox

    inbox_data = json_read(inbox_file, {})
    inbox = Inbox.from_dict(inbox_data) if inbox_data else Inbox(agent=to)
    msg = build_message(
        "mailbus", to, content, MsgType.NOTICE,
        Priority.URGENT if priority == "urgent" else Priority.NORMAL,
    )
    entry = msg.to_dict()
    if msg_id:
        entry["id"] = msg_id
    action = dict(entry.get("action") or {})
    if no_llm:
        action["no_llm"] = True
        action["execute"] = False
    entry["action"] = action
    inbox.messages.append(entry)
    inbox.has_unread = True
    json_write(inbox_file, inbox.to_dict())


def _recent_patrol_notice(data_dir: str, agent: str = "lingxun", hours: float = 1.0) -> bool:
    """是否已有近期 patrol notice（避免 scheduler 重复写入）。"""
    from datetime import datetime, timezone, timedelta
    from .models import Inbox
    from .tracker import _parse_iso_dt

    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
    data = json_read(inbox_file, {}, ttl=0)
    if not data:
        return False
    inbox = Inbox.from_dict(data)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    for m in inbox.messages:
        mid = inbox.msg_field(m, "id", "")
        content = inbox.msg_field(m, "content", "") or ""
        if not (mid.startswith("patrol-") or "执行定时巡检" in content):
            continue
        st = (inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", "")).lower()
        if st in ("done", "closed", "archived"):
            continue
        created = inbox.msg_field(m, "created_at", "")
        if created:
            try:
                if _parse_iso_dt(created).astimezone(timezone.utc) >= cutoff:
                    return True
            except Exception:
                return True
    return False


def run_lingxun_patrol(data_dir: str) -> int:
    if _recent_patrol_notice(data_dir, "lingxun", hours=1.0):
        print(f"[patrol] skip — recent patrol notice exists {_now_iso()}")
        return 0
    import time as _time
    from lib.constants import DEFAULT_API_BASE

    content = (
        "⏰ 执行定时巡检（零 LLM）\n"
        f"Dashboard: {DEFAULT_API_BASE}/\n"
        "API: GET /api/status · GET /api/tasks\n"
        "书面报告请人工在 Cursor 触发；mailbus 不 spawn CLI。"
    )
    try:
        _append_inbox_notice(
            data_dir, "lingxun", content,
            msg_id=f"patrol-{int(_time.time())}",
            no_llm=True,
        )
        print(f"[patrol] lingxun notice queued (no-llm) {_now_iso()}")
        return 0
    except Exception as exc:
        print(f"[patrol] error: {exc}", file=sys.stderr)
        return 1


def run_pipeline_watchdog(data_dir: str) -> int:
    root = _mail_root(data_dir)
    script = os.path.join(root, "tools", "pipeline-watchdog.py")
    if not os.path.isfile(script):
        return 0
    try:
        r = subprocess.run(
            [sys.executable, script, "--data-dir", data_dir],
            cwd=root, capture_output=True, text=True, timeout=120,
        )
        if r.stdout:
            print(r.stdout.rstrip())
        return r.returncode
    except Exception as exc:
        print(f"[pipeline-watchdog] error: {exc}", file=sys.stderr)
        return 1


def run_platform_scout(data_dir: str) -> int:
    """按 leads-sources.json 抓取线索 raw 快照。"""
    root = _mail_root(data_dir)
    script = os.path.join(root, "tools", "platform-scout.py")
    if not os.path.isfile(script):
        return 0
    try:
        r = subprocess.run(
            [sys.executable, script, "--data-dir", data_dir],
            cwd=root, capture_output=True, text=True, timeout=180,
        )
        if r.stdout:
            print(r.stdout.rstrip())
        if r.returncode != 0 and r.stderr:
            print(r.stderr.rstrip(), file=sys.stderr)
        return r.returncode
    except subprocess.TimeoutExpired:
        print("[platform-scout] timeout", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"[platform-scout] error: {exc}", file=sys.stderr)
        return 1


def run_pipeline_repair(data_dir: str) -> int:
    """扫描 running pipeline 任务，清理 stale queue / 报告 phantom。"""
    from .tracker import TaskTracker

    root = _mail_root(data_dir)
    script = os.path.join(root, "tools", "repair-pipeline-stuck.py")
    if not os.path.isfile(script):
        return 0
    tra = TaskTracker(data_dir)
    running = [t for t in tra.list_all() if t.get("status") == "running"]
    if not running:
        return 0
    rc = 0
    for t in running[:10]:
        tid = t.get("task_id", "")
        if not tid:
            continue
        try:
            r = subprocess.run(
                [sys.executable, script, "--data-dir", data_dir, "--task-id", tid, "--fix"],
                cwd=root, capture_output=True, text=True, timeout=90,
            )
            if r.stdout.strip():
                print(r.stdout.strip())
            if r.returncode:
                rc = r.returncode
        except Exception as exc:
            print(f"[pipeline-repair] {tid}: {exc}", file=sys.stderr)
            rc = 1
    return rc


def run_intake_bridge(data_dir: str) -> int:
    from .intake.spawn_rules import bridge_reconcile

    try:
        out = bridge_reconcile(data_dir)
        print(f"[intake-bridge] {out.get('status', '?')} spawned={out.get('spawned', 0)}")
        return 0 if out.get("status") == "ok" else 1
    except Exception as exc:
        print(f"[intake-bridge] error: {exc}", file=sys.stderr)
        return 1


def run_triage_inbox(data_dir: str, config: dict | None = None) -> int:
    from .internal_llm.triage import triage_inbox_anomaly

    try:
        cfg = config or json_read(os.path.join(data_dir, "config.json"), {})
        out = triage_inbox_anomaly(data_dir, cfg)
        print(f"[triage-inbox] {out.get('status')} anomalies={out.get('anomalies', 0)}")
        return 0 if out.get("status") in ("ok", "skipped") else 1
    except Exception as exc:
        print(f"[triage-inbox] error: {exc}", file=sys.stderr)
        return 1


def run_agent_cli_version_check(data_dir: str) -> int:
    """探测 Docker 容器内 agent CLI 版本，写入 store/system/agent-versions.json。"""
    import subprocess

    from .agent_adapters import container_for_service, get_adapter
    from .utils import json_read, json_write, _now_iso

    config = json_read(os.path.join(data_dir, "config.json"), {})
    agents = config.get("agents") or {}
    probes: dict[str, dict] = {}
    services_done: set[str] = set()
    version_cmd_by_type = {
        "hermes": "hermes --version",
        "hermes_profile": "hermes --version",
        "openclaw": "openclaw --version",
        "opencode": "opencode --version",
        "codex": "codex --version",
        "cline": "cline --version",
    }

    for name, cfg in agents.items():
        atype = cfg.get("type", "none")
        adapter = get_adapter(atype)
        if not adapter:
            continue
        svc = (cfg.get("docker") or {}).get("service") or adapter.container_service or name
        if svc in services_done:
            continue
        services_done.add(svc)
        version_cmd = version_cmd_by_type.get(atype, "")
        if not version_cmd:
            continue
        container = container_for_service(svc)
        try:
            r = subprocess.run(
                ["docker", "exec", container, "bash", "-lc", version_cmd],
                capture_output=True,
                text=True,
                timeout=15,
            )
            probes[svc] = {
                "container": container,
                "type": atype,
                "version": (r.stdout or r.stderr or "").strip()[:500],
                "ok": r.returncode == 0,
                "checked_at": _now_iso(),
            }
        except Exception as exc:
            probes[svc] = {
                "container": container,
                "type": atype,
                "error": str(exc),
                "ok": False,
                "checked_at": _now_iso(),
            }

    out_dir = os.path.join(data_dir, "system")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "agent-versions.json")
    payload = {"updated_at": _now_iso(), "services": probes}
    json_write(out_path, payload)
    ok_count = sum(1 for v in probes.values() if v.get("ok"))
    print(f"[agent-cli-version-check] {ok_count}/{len(probes)} ok -> {out_path}")
    return 0 if ok_count == len(probes) or not probes else 1


def run_daily_report(data_dir: str) -> int:
    from lib.constants import DEFAULT_API_BASE

    today = datetime.now(TZ_CN).strftime("%Y-%m-%d")
    content = (
        f"📊 生成日报提醒（零 LLM）— {today}\n"
        f"Dashboard: {DEFAULT_API_BASE}/\n"
        f"如需 md 报告请人工写入 store/reports/daily/{today}.md"
    )
    try:
        _append_inbox_notice(
            data_dir, "lingxun", content,
            msg_id=f"patrol-daily-{today.replace('-', '')}",
            no_llm=True,
        )
        print(f"[daily-report] lingxun notice queued (no-llm) {today}")
        return 0
    except Exception as exc:
        print(f"[daily-report] error: {exc}", file=sys.stderr)
        return 1
