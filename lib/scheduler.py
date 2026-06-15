"""mailbus 内置调度中枢 — 替代 WSL crontab。"""

from __future__ import annotations

import fcntl
import io
import os
import sys
import threading
import time
import traceback
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List, Optional

from .utils import json_read, json_write, _now_iso

TZ_CN = timezone(timedelta(hours=8))

DEFAULT_JOBS = [
    {"id": "scan", "enabled": True, "interval_seconds": 60, "lock": "mailbus-scan"},
    {"id": "memory_bridge", "enabled": True, "interval_seconds": 60, "lock": "mailbus-bridge", "limit": 20},
    {"id": "pipeline_watchdog", "enabled": True, "interval_seconds": 300, "lock": "mailbus-watchdog"},
    {"id": "lingxun_patrol", "enabled": True, "interval_seconds": 900},
    {"id": "daily_report", "enabled": True, "cron": "30 23 * * *"},
    {"id": "log_rotate", "enabled": True, "cron": "0 3 * * *"},
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
        data_dir, limit=int(job.get("limit", 20))
    )
    _JOB_RUNNERS["pipeline_watchdog"] = lambda data_dir, cfg, job: job_mod.run_pipeline_watchdog(data_dir)
    _JOB_RUNNERS["lingxun_patrol"] = lambda data_dir, cfg, job: job_mod.run_lingxun_patrol(data_dir)
    _JOB_RUNNERS["daily_report"] = lambda data_dir, cfg, job: job_mod.run_daily_report(data_dir)
    _JOB_RUNNERS["log_rotate"] = lambda data_dir, cfg, job: job_mod.run_log_rotate(data_dir)


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


def _should_run(job: dict, job_state: dict, now: float, now_dt: datetime) -> bool:
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
    interval = int(job.get("interval_seconds", 60))
    return (now - last) >= interval


def _acquire_lock(lock_name: str):
    path = f"/tmp/{lock_name}.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


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
    fd = _acquire_lock(lock_name) if lock_name else None
    if lock_name and fd is None:
        return

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
    finally:
        if fd is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

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
        for job in sched_cfg.get("jobs", []):
            jid = job.get("id")
            if not jid:
                continue
            js = job_states.setdefault(jid, {})
            if _should_run(job, js, now, now_dt):
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
