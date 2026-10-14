"""Aggregate pipeline failover metrics from task chain dispatch_meta."""
from __future__ import annotations

import os
from collections import Counter
from typing import Any

from lib.infra.utils import json_read, resolve_paths


def _is_failover_meta(meta: Any) -> bool:
    if not isinstance(meta, dict):
        return False
    method = str(meta.get("method") or "")
    return method == "pipeline_role_failover" or bool(meta.get("failover_at")) or bool(
        meta.get("failover_from")
    )


def collect_failover_metrics(data_dir: str, *, limit_tasks: int = 500) -> dict[str, Any]:
    """Scan store/tasks/*.json and summarize failover events on chain steps."""
    paths = resolve_paths(data_dir)
    tasks_dir = paths.get("tasks") or os.path.join(data_dir, "tasks")
    events: list[dict[str, Any]] = []
    by_from: Counter[str] = Counter()
    by_to: Counter[str] = Counter()
    by_tier: Counter[str] = Counter()
    by_reason: Counter[str] = Counter()
    tasks_with = 0
    scanned = 0

    if not os.path.isdir(tasks_dir):
        return {
            "scanned_tasks": 0,
            "tasks_with_failover": 0,
            "event_count": 0,
            "by_from_agent": {},
            "by_to_agent": {},
            "by_tier": {},
            "by_reason_prefix": {},
            "recent": [],
        }

    names = sorted(
        (n for n in os.listdir(tasks_dir) if n.endswith(".json") and not n.startswith(".")),
        reverse=True,
    )[: max(1, int(limit_tasks))]

    for name in names:
        scanned += 1
        task = json_read(os.path.join(tasks_dir, name), {})
        if not isinstance(task, dict):
            continue
        tid = str(task.get("task_id") or name[:-5])
        hit = False
        for step in task.get("chain") or []:
            if not isinstance(step, dict):
                continue
            meta = step.get("dispatch_meta")
            if not _is_failover_meta(meta):
                # also count failover_tried as soft signal
                tried = step.get("failover_tried") or []
                if not tried:
                    continue
                meta = {
                    "method": "failover_tried",
                    "failover_from": (tried[-1] if tried else ""),
                    "failover_at": step.get("updated_at") or task.get("updated_at") or "",
                    "reason": "tried_list",
                }
            hit = True
            frm = str(meta.get("failover_from") or "")
            to = str(step.get("to_agent") or step.get("to_person") or meta.get("failover_to") or "")
            tier = str(meta.get("failover_tier") or "unknown")
            reason = str(meta.get("reason") or "")[:80]
            reason_key = reason.split(" ", 1)[0] if reason else "unspecified"
            by_from[frm or "?"] += 1
            by_to[to or "?"] += 1
            by_tier[tier] += 1
            by_reason[reason_key] += 1
            events.append(
                {
                    "task_id": tid,
                    "step_id": step.get("step_id"),
                    "from_agent": frm,
                    "to_agent": to,
                    "tier": tier,
                    "reason": reason,
                    "at": meta.get("failover_at") or task.get("updated_at") or "",
                    "tried": list(step.get("failover_tried") or []),
                }
            )
        if hit:
            tasks_with += 1

    events.sort(key=lambda e: str(e.get("at") or ""), reverse=True)
    return {
        "scanned_tasks": scanned,
        "tasks_with_failover": tasks_with,
        "event_count": len(events),
        "by_from_agent": dict(by_from.most_common(20)),
        "by_to_agent": dict(by_to.most_common(20)),
        "by_tier": dict(by_tier),
        "by_reason_prefix": dict(by_reason.most_common(20)),
        "recent": events[:40],
    }
