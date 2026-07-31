"""A2A 降级告警 jsonl。"""
from __future__ import annotations

from lib.adapters.clock import now_dt, now_ts, now_utc_dt
import os
from datetime import datetime, timezone
from typing import Any

from ..utils import jsonl_append, _now_iso
from .types import DispatchContext


def _iso_week() -> str:
    dt = now_utc_dt()
    return f"{dt.isocalendar().year}-W{dt.isocalendar().week:02d}"


def log_a2a_fallback(
    data_dir: str,
    ctx: DispatchContext,
    attempts: list[dict[str, Any]],
    *,
    last_error: str = "",
) -> str:
    """追加 store/errors/a2a-fallback-{week}.jsonl，返回写入路径。"""
    errors_dir = os.path.join(data_dir, "errors")
    os.makedirs(errors_dir, exist_ok=True)
    path = os.path.join(errors_dir, f"a2a-fallback-{_iso_week()}.jsonl")
    line = {
        "event": "a2a_retries_exhausted",
        "task_id": ctx.task_id,
        "step_id": ctx.step_id,
        "to_agent": ctx.to_agent,
        "attempts": len([a for a in attempts if a.get("channel") == "a2a_standard"]),
        "last_error": last_error,
        "fallback_channel": "file_bus",
        "ts": _now_iso(),
        "notify": ["dashboard", "lingxun_inbox"],
        "transport_attempts": attempts,
    }
    jsonl_append(path, line)
    return path


def log_input_required_timeout(
    data_dir: str,
    *,
    task_id: str,
    step_id: str = "",
    hq_id: str = "",
    hq_type: str = "",
    age_sec: int = 0,
) -> str:
    errors_dir = os.path.join(data_dir, "errors")
    os.makedirs(errors_dir, exist_ok=True)
    path = os.path.join(errors_dir, f"a2a-fallback-{_iso_week()}.jsonl")
    line = {
        "event": "input_required_timeout",
        "task_id": task_id,
        "step_id": step_id,
        "hq_id": hq_id,
        "hq_type": hq_type,
        "age_sec": age_sec,
        "ts": _now_iso(),
        "notify": ["dashboard", "lingxun_inbox"],
    }
    jsonl_append(path, line)
    return path
