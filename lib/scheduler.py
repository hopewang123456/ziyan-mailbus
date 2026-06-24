"""mailbus 内置调度中枢 — 替代 WSL crontab。"""

from __future__ import annotations

import io
import os
import sys
import threading
import time
import traceback
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List, Optional

from .utils import json_read, json_write, _now_iso, named_lock

TZ_CN = timezone(timedelta(hours=8))

DEFAULT_JOBS = [
    {"id": "scan", "enabled": True, "interval_seconds": 180},
    {"id": "memory_bridge", "enabled": True, "interval_seconds": 120, "lock": "mailbus-bridge", "limit": 5},
    {"id": "agentmemory_watchdog", "enabled": True, "interval_seconds": 180, "lock": "am-watchdog"},
    {"id": "intake-bridge", "enabled": True, "interval_seconds": 60, "lock": "mailbus-intake-bridge"},
    {"id": "platform-scout", "enabled": True, "interval_seconds": 21600, "lock": "mailbus-platform-scout"},
    {"id": "triage-inbox", "enabled": True, "interval_seconds": 900, "lock": "mailbus-triage-inbox"},
    {"id": "pipeline_watchdog", "enabled": True, "interval_seconds": 300, "lock": "mailbus-watchdog"},
    {"id": "pipeline-repair", "enabled": True, "interval_seconds": 600, "lock": "mailbus-pipeline-repair"},
    {"id": "lingxun_patrol", "enabled": True, "interval_seconds": 3600},
    {"id": "daily_report", "enabled": True, "cron": "30 23 * * *"},
    {"id": "log_rotate", "enabled": True, "cron": "0 3 * * *"},
    {"id": "agent_cli_version_check", "enabled": True, "interval_seconds": 86400, "lock": "mailbus-agent-versions"},
]

_JOB_RUNNERS: Dict[str, Callable] = {}

# 进程内状态（API /api/status 可读）
_hub_state: Dict[str, Any] = {
    "running": False,
    "started_at": None,
    "jobs": {},
    "last_error": None,
}
_state_lock = threading.Lock()


def get_scheduler_status() -> dict:
    with _state_lock:
        return dict(_hub_state)


def _register_runners():
    if _JOB_RUNNERS:
        return
    from . import jobs as job_mod

    _JOB_RUNNERS["scan"] = lambda data_dir, cfg, job: job_mod.run_scan(data_dir, cfg, quiet=True)
    _JOB_RUNNERS["memory_bridge"] = lambda data_dir, cfg, job: job_mod.run_memory_bridge(
        data_dir,
        limit=int(job.get("limit") or (cfg.get("token_budget") or {}).get("memory_bridge_limit", 5)),
    )
    _JOB_RUNNERS["pipeline_watchdog"] = lambda data_dir, cfg, job: job_mod.run_pipeline_watchdog(data_dir)
    _JOB_RUNNERS["pipeline-repair"] = lambda data_dir, cfg, job: job_mod.run_pipeline_repair(data_dir)
    _JOB_RUNNERS["intake-bridge"] = lambda data_dir, cfg, job: job_mod.run_intake_bridge(data_dir)
    _JOB_RUNNERS["platform-scout"] = lambda data_dir, cfg, job: job_mod.run_platform_scout(data_dir)
    _JOB_RUNNERS["triage-inbox"] = lambda data_dir, cfg, job: job_mod.run_triage_inbox(data_dir, cfg)
    _JOB_RUNNERS["lingxun_patrol"] = lambda data_dir, cfg, job: job_mod.run_lingxun_patrol(data_dir)
    _JOB_RUNNERS["daily_report"] = lambda data_dir, cfg, job: job_mod.run_daily_report(data_dir)
    _JOB_RUNNERS["log_rotate"] = lambda data_dir, cfg, job: job_mod.run_log_rotate(data_dir)
    _JOB_RUNNERS["agent_cli_version_check"] = lambda data_dir, cfg, job: job_mod.run_agent_cli_version_check(data_dir)
    _JOB_RUNNERS["agentmemory_watchdog"] = lambda data_dir, cfg, job: job_mod.run_agentmemory_watchdog(data_dir)


def load_scheduler_config(config: dict) -> dict:
    sched = config.get("scheduler") or {}
    if not isinstance(sched, dict):
        sched = {}
    jobs = sched.get("jobs")
    if not jobs:
        jobs = DEFAULT_JOBS
    return {
        "enabled": sched.get("enabled", True),
        "tick_seconds": max(5, int(sched.get("tick_seconds", 10))),
        "log_file": sched.get("log_file", "scheduler.log"),
        "mirror_cron_log": sched.get("mirror_cron_log", True),
        "jobs": jobs,
    }


def _cron_field_matches(field: str, val: int, *, is_dow: bool = False) -> bool:
    if field == "*":
        return True
    if not field.isdigit():
        return False
    n = int(field)
    if is_dow:
        py_dow = 6 if n in (0, 7) else n - 1  # cron 0/7=Sun → weekday 6
        return py_dow == val
    return n == val


def _cron_matches(expr: str, now: datetime) -> bool:
    """简易 cron 匹配：分 时 日 月 周（仅支持 * 与数字）。"""
    parts = expr.strip().split()
    if len(parts) != 5:
        return False
    minute, hour, dom, month, dow = parts
    checks = [
        (minute, now.minute, False),
        (hour, now.hour, False),
        (dom, now.day, False),
        (month, now.month, False),
        (dow, now.weekday(), True),
    ]
    return all(_cron_field_matches(f, v, is_dow=dow_flag) for f, v, dow_flag in checks)


def _should_run(
    job: dict,
    job_state: dict,
    now: float,
    now_dt: datetime,
    *,
    effective_interval: Optional[int] = None,
) -> bool:
    if not job.get("enabled", True):
        return False
    last = job_state.get("last_run_at", 0)
    cron = job.get("cron")
    if cron:
        # cron job：同一分钟只跑一次
        minute_key = now_dt.strftime("%Y-%m-%d %H:%M")
        if job_state.get("last_cron_minute") == minute_key:
            return False
        if _cron_matches(cron, now_dt):
            return True
        return False
    interval = int(
        effective_interval if effective_interval is not None
        else job.get("interval_seconds", 60)
    )
    return (now - last) >= interval


def _log_lines(data_dir: str, sched_cfg: dict, lines: str):
    log_name = sched_cfg.get("log_file", "scheduler.log")
    paths = [os.path.join(data_dir, log_name)]
    if sched_cfg.get("mirror_cron_log", True):
        paths.append(os.path.join(data_dir, "cron.log"))
    for path in paths:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(lines)
        except OSError:
            pass


def _run_job(job: dict, data_dir: str, config: dict, sched_cfg: dict) -> None:
    jid = job.get("id", "?")
    _register_runners()
    runner = _JOB_RUNNERS.get(jid)
    if not runner:
        return

    lock_name = job.get("lock", f"mailbus-job-{jid}")
    if lock_name:
        with named_lock(lock_name, blocking=False) as acquired:
            if not acquired:
                return
            _run_job_locked(job, jid, runner, data_dir, config, sched_cfg)
    else:
        _run_job_locked(job, jid, runner, data_dir, config, sched_cfg)


def _run_job_locked(job: dict, jid: str, runner, data_dir: str, config: dict, sched_cfg: dict) -> None:
    started = time.time()
    ts = _now_iso()
    header = f"\n[{ts}] scheduler job={jid} start\n"
    rc = 0
    body = ""
    try:
        old_stdout, old_stderr = sys.stdout, sys.stderr
        capture = io.StringIO()
        try:
            sys.stdout = capture
            sys.stderr = capture
            rc = runner(data_dir, config, job)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
        body = capture.getvalue()
    except Exception:
        body = traceback.format_exc()
        rc = 1

    elapsed = round(time.time() - started, 2)
    footer = f"[{_now_iso()}] scheduler job={jid} done rc={rc} elapsed={elapsed}s\n"
    if body:
        _log_lines(data_dir, sched_cfg, header + body + footer)
    else:
        _log_lines(data_dir, sched_cfg, header + footer)

    now = time.time()
    now_dt = datetime.now(TZ_CN)
    with _state_lock:
        st = _hub_state["jobs"].setdefault(jid, {})
        st["last_run_at"] = now
        st["last_run_iso"] = _now_iso()
        st["last_rc"] = rc
        st["last_elapsed_s"] = elapsed
        if job.get("cron"):
            st["last_cron_minute"] = now_dt.strftime("%Y-%m-%d %H:%M")
        if rc != 0:
            _hub_state["last_error"] = {"job": jid, "at": _now_iso(), "rc": rc}


def _scheduler_loop(data_dir: str, config: dict, sched_cfg: dict, stop: threading.Event):
    state_path = os.path.join(data_dir, "scheduler-state.json")
    persisted = json_read(state_path, {})
    job_states = persisted.get("jobs", {})

    tick = sched_cfg["tick_seconds"]
    with _state_lock:
        _hub_state["running"] = True
        _hub_state["started_at"] = _now_iso()
        _hub_state["jobs"] = job_states

    _log_lines(data_dir, sched_cfg, f"[{_now_iso()}] scheduler hub started tick={tick}s\n")

    while not stop.is_set():
        now = time.time()
        now_dt = datetime.now(TZ_CN)
        agents = config.get("agents") or {}
        scan_interval = None
        activity = {}
        try:
            from .token_budget import (
                effective_scan_interval_seconds,
                measure_mailbus_activity,
            )
            activity = measure_mailbus_activity(data_dir, agents, config)
            scan_interval = effective_scan_interval_seconds(config, activity)
            with _state_lock:
                _hub_state["token_activity"] = activity
                _hub_state["scan_interval_effective"] = scan_interval
        except Exception:
            pass

        for job in sched_cfg.get("jobs", []):
            jid = job.get("id")
            if not jid:
                continue
            js = job_states.setdefault(jid, {})
            eff = scan_interval if jid == "scan" else None
            if _should_run(job, js, now, now_dt, effective_interval=eff):
                _run_job(job, data_dir, config, sched_cfg)
                with _state_lock:
                    js.update(_hub_state.get("jobs", {}).get(jid, {}))
        try:
            json_write(state_path, {"updated_at": _now_iso(), "jobs": job_states})
        except OSError:
            pass
        stop.wait(tick)

    with _state_lock:
        _hub_state["running"] = False
    _log_lines(data_dir, sched_cfg, f"[{_now_iso()}] scheduler hub stopped\n")


class SchedulerHub:
    def __init__(self, data_dir: str, config: dict):
        self.data_dir = data_dir
        self.config = config
        self.sched_cfg = load_scheduler_config(config)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if not self.sched_cfg.get("enabled", True):
            print("⏸️  scheduler 已禁用（config.scheduler.enabled=false）")
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=_scheduler_loop,
            args=(self.data_dir, self.config, self.sched_cfg, self._stop),
            name="mailbus-scheduler",
            daemon=True,
        )
        self._thread.start()
        jobs = [j.get("id") for j in self.sched_cfg.get("jobs", []) if j.get("enabled", True)]
        print(f"⏱️  scheduler 已启动: {', '.join(jobs)} (tick={self.sched_cfg['tick_seconds']}s)")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
