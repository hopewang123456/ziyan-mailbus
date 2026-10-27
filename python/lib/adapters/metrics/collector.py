"""metrics collector — 按 manifest 口径现算 point 值（数据源=既有服务，不重复造采集）。"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from lib.adapters.metrics.manifest import load_manifest

_ACTIVE = {"running", "pending", "blocked"}
_FAILED = {"failed", "timeout"}
_TERMINAL_MSG = {"done", "closed", "rejected", "failed", "archived", "sent", "acknowledged"}


def collect_point(metric_id: str, data_dir: str = "") -> Dict[str, Any]:
    """单指标现算。未登记 id → {error: unknown_metric}；数据源异常 → {error: ...}（不静默 0）。"""
    entry = None
    for m in load_manifest(data_dir).get("metrics") or []:
        if m.get("id") == metric_id:
            entry = m
            break
    if entry is None:
        return {"metric": metric_id, "error": "unknown_metric"}
    try:
        value = _compute(str(entry.get("source")), metric_id, data_dir)
        return {"metric": metric_id, "value": value, "unit": entry.get("unit") or "count"}
    except Exception as exc:  # 数据源缺失等 — 显式错误（B 系列纪律：不静默）
        return {"metric": metric_id, "error": str(exc)[:200]}


def collect_all_points(data_dir: str = "") -> List[Dict[str, Any]]:
    return [collect_point(str(m.get("id")), data_dir) for m in load_manifest(data_dir).get("metrics") or []]


def _compute(source: str, metric_id: str, data_dir: str) -> float:
    if source == "tasks":
        return _tasks(metric_id, data_dir)
    if source == "messages":
        return _messages(metric_id, data_dir)
    if source == "agents":
        return _agents(metric_id, data_dir)
    if source == "tokens":
        return _tokens(metric_id, data_dir)
    if source == "alerts":
        return _alerts(metric_id, data_dir)
    if source == "human_queue":
        return _human_queue(metric_id, data_dir)
    if source == "tasks_b":
        return _tasks_b(metric_id, data_dir)
    raise ValueError(f"unknown source: {source}")


def _tasks(metric_id: str, data_dir: str) -> float:
    from lib.composition import task_tracker_factory  # 惰性门面，避免 adapters→application 反向

    tasks = task_tracker_factory()(data_dir).list_all()
    if metric_id == "tasks.active":
        return float(sum(1 for t in tasks if (t.get("status") or "") in _ACTIVE))
    if metric_id == "tasks.failed_today":
        from lib.infra.utils import parse_iso_dt
        from lib.infra.clock import now_dt

        today = str(now_dt())[:10]
        n = 0
        for t in tasks:
            if (t.get("status") or "") not in _FAILED:
                continue
            ts = str(t.get("updated_at") or t.get("created_at") or "")
            if ts[:10] == today:
                n += 1
        return float(n)
    raise ValueError(f"tasks source has no metric {metric_id}")


def _messages(metric_id: str, data_dir: str) -> float:
    import os as _os

    from lib.infra.utils import json_read, resolve_paths

    paths = resolve_paths(data_dir)
    inbox_root = paths["inbox"]
    total = 0
    unread = 0
    if _os.path.isdir(inbox_root):
        for agent in _os.listdir(inbox_root):
            doc = json_read(_os.path.join(inbox_root, agent, "inbox.json"), {})
            msgs = doc.get("messages") or []
            total += len(msgs)
            unread += sum(
                1
                for m in msgs
                if (m.get("state") or m.get("status") or "") not in _TERMINAL_MSG
            )
    if metric_id == "bus.messages_total":
        return float(total)
    if metric_id == "bus.unread":
        return float(unread)
    raise ValueError(f"messages source has no metric {metric_id}")


def _agents(metric_id: str, data_dir: str) -> float:
    import os as _os

    from lib.adapters.ops.heartbeat import is_online
    from lib.infra.builtin_identities import merge_into_agents
    from lib.infra.utils import json_read

    cfg = json_read(_os.path.join(data_dir, "config.json"), {})

    agents = merge_into_agents(dict(cfg.get("agents") or {}), data_dir)
    if metric_id == "agents.total":
        return float(len(agents))
    if metric_id == "agents.online":
        return float(sum(1 for a in agents if is_online(data_dir, a)))
    raise ValueError(f"agents source has no metric {metric_id}")


def _tokens(metric_id: str, data_dir: str) -> float:
    from lib.infra.token_ledger import today_summary

    summary = today_summary(data_dir)
    # 口径=/api/tokens/summary 估算口径（estimates），回执 usage 为上报口径
    for key in ("estimated_total", "estimates_total", "total_estimated", "total"):
        if key in summary:
            return float(summary[key] or 0)
    return float(sum(float(e.get("estimated") or 0) for e in summary.get("entries") or []))


def _alerts(metric_id: str, data_dir: str) -> float:
    from lib.adapters.ops.alerter import get_recent_alerts

    return float(len(get_recent_alerts(data_dir, limit=50)))


def _human_queue(metric_id: str, data_dir: str) -> float:
    from lib.adapters.orchestration.human_queue import load_queue

    doc = load_queue(data_dir)
    return float(sum(1 for i in (doc.get("items") or []) if i.get("status") == "pending"))


def _tasks_b(metric_id: str, data_dir: str) -> float:
    """P5 B 类口径：工单周期 + 人工介入（7 天窗口）。"""
    import datetime as _dt
    import os as _os

    now = _dt.datetime.now(_dt.timezone.utc)
    week_ago = now - _dt.timedelta(days=7)

    def _parse(ts: str) -> _dt.datetime | None:
        from lib.infra.utils import parse_iso_dt

        dt = parse_iso_dt(str(ts or ""))
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_dt.timezone.utc)
        return dt

    if metric_id == "tasks.interventions_week":
        # 口径：audit.jsonl 近 7 天 human_gate.resolve 事件数
        count = 0
        path = _os.path.join(data_dir, "system", "audit.jsonl")
        if _os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if ev.get("event") != "human_gate.resolve":
                        continue
                    ts = _parse(str(ev.get("ts") or ""))
                    if ts and ts >= week_ago:
                        count += 1
        return float(count)

    if metric_id == "tasks.cycle_avg_minutes":
        # 口径：近 7 天终态(success)任务 created_at→updated_at 平均分钟数
        from lib.composition import task_tracker_factory

        durations = []
        for t in task_tracker_factory()(data_dir).list_all():
            if (t.get("status") or "") != "success":
                continue
            updated = _parse(str(t.get("updated_at") or ""))
            created = _parse(str(t.get("created_at") or ""))
            if not updated or not created or updated < week_ago:
                continue
            durations.append((updated - created).total_seconds() / 60.0)
        if not durations:
            return 0.0
        return round(sum(durations) / len(durations), 1)

    raise ValueError(f"tasks_b source has no metric {metric_id}")
