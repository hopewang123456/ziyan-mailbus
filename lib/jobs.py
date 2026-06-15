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
from .utils import build_message, json_write, resolve_paths, _now_iso

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
    try:
        r = subprocess.run(
            [sys.executable, script, "--data-dir", data_dir, "--limit", str(limit)],
            cwd=root, env=env, capture_output=True, text=True, timeout=180,
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


def run_lingxun_patrol(data_dir: str) -> int:
    content = (
        "⏰ 执行定时巡检 — 请检查所有 Agent inbox 状态、任务进度，生成巡检报告。"
        "回复给发件人 mailbus。"
    )
    try:
        _append_inbox_task(data_dir, "lingxun", content)
        print(f"[patrol] lingxun task queued {_now_iso()}")
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


def run_daily_report(data_dir: str) -> int:
    today = datetime.now(TZ_CN).strftime("%Y-%m-%d")
    content = (
        f"📊 生成日报 — 今天是 {today}。请汇总今日巡检结果，生成日报写入 "
        f"store/reports/daily/{today}.md。内容包括：整体概览（消息总数/完成数/超时数）、"
        "Agent活跃度统计、需要关注的问题。"
    )
    try:
        _append_inbox_task(data_dir, "lingxun", content, priority="normal")
        print(f"[daily-report] lingxun task queued {today}")
        return 0
    except Exception as exc:
        print(f"[daily-report] error: {exc}", file=sys.stderr)
        return 1
