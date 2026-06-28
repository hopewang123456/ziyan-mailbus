"""Task 级锁 — store/locks/task-{task_id}.json（与 scan/file lock 命名空间分离）。

设计说明（P3-S44）：push 路径在写入 inbox/work-order 后**立即 release**，
避免 push 失败时锁泄漏；scan/push 竞态由 inbox 消息 state + task FSM 占步约束。
recover continue 持锁贯穿 repush；若需「单写者贯穿 step 执行」可后续改为 step 完成时 release。
"""

from __future__ import annotations

import os
from typing import Any, Optional

from .utils import _now_iso, file_lock, json_read, json_write


def task_lock_path(data_dir: str, task_id: str) -> str:
    return os.path.join(data_dir, "locks", f"task-{task_id}.json")


def read_task_lock(data_dir: str, task_id: str) -> Optional[dict]:
    path = task_lock_path(data_dir, task_id)
    if not os.path.isfile(path):
        return None
    data = json_read(path, {})
    return data if isinstance(data, dict) and data else None


def _is_stale(lock: dict, *, ttl_seconds: float) -> bool:
    if not lock or not lock.get("holder"):
        return True
    acquired = lock.get("acquired_at") or ""
    if not acquired:
        return True
    try:
        from .tracker import _parse_iso_dt
        from datetime import datetime, timezone

        ts = _parse_iso_dt(acquired)
        age = (datetime.now(timezone.utc) - ts).total_seconds()
        return age > ttl_seconds
    except Exception:
        return True


def acquire_task_lock(
    data_dir: str,
    task_id: str,
    holder: str,
    *,
    ttl_seconds: float = 3600.0,
    meta: Optional[dict] = None,
) -> bool:
    """获取 task 锁；同一 holder 可重入；过期锁可被抢占。"""
    os.makedirs(os.path.join(data_dir, "locks"), exist_ok=True)
    path = task_lock_path(data_dir, task_id)
    with file_lock(path=path):
        existing = read_task_lock(data_dir, task_id)
        if existing and not _is_stale(existing, ttl_seconds=ttl_seconds):
            if existing.get("holder") == holder:
                return True
            return False
        payload: dict[str, Any] = {
            "task_id": task_id,
            "holder": holder,
            "acquired_at": _now_iso(),
            "ttl_seconds": ttl_seconds,
        }
        if meta:
            payload["meta"] = meta
        json_write(path, payload)
        return True


def release_task_lock(data_dir: str, task_id: str, holder: str) -> bool:
    """释放 task 锁；仅 holder 可释放。"""
    path = task_lock_path(data_dir, task_id)
    if not os.path.isfile(path):
        return True
    with file_lock(path=path):
        existing = read_task_lock(data_dir, task_id)
        if not existing:
            return True
        if existing.get("holder") != holder:
            return False
        try:
            os.remove(path)
        except OSError:
            return False
        return True


def task_lock_holder(data_dir: str, task_id: str) -> Optional[str]:
    lock = read_task_lock(data_dir, task_id)
    if not lock:
        return None
    ttl = float(lock.get("ttl_seconds") or 3600)
    if _is_stale(lock, ttl_seconds=ttl):
        return None
    return lock.get("holder")
