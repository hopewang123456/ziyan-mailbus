"""Inbox 异常 triage — 扫描 stale/duplicate 消息，可选 LLM 摘要。"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from ..utils import json_read, resolve_paths, _now_iso
from ..jobs import _append_inbox_notice

TZ_CN = timezone(timedelta(hours=8))
_STALE_HOURS = 24


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def scan_inbox_anomalies(data_dir: str, *, stale_hours: int = _STALE_HOURS) -> List[dict]:
    """只读扫描，返回 anomaly 列表。"""
    paths = resolve_paths(data_dir)
    inbox_root = paths.get("inbox") or os.path.join(data_dir, "inbox")
    if not os.path.isdir(inbox_root):
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=stale_hours)
    anomalies: List[dict] = []
    seen_ids: Dict[str, str] = {}

    for agent in os.listdir(inbox_root):
        agent_dir = os.path.join(inbox_root, agent)
        if not os.path.isdir(agent_dir):
            continue
        inbox_file = os.path.join(agent_dir, "inbox.json")
        data = json_read(inbox_file, {})
        msgs = data.get("messages") or []
        for m in msgs:
            if not isinstance(m, dict):
                continue
            mid = m.get("msg_id") or m.get("id") or ""
            state = (m.get("state") or m.get("status") or "").lower()
            if state in ("done", "closed", "rejected", "failed", "archived", "sent"):
                continue
            if mid:
                if mid in seen_ids:
                    anomalies.append({
                        "type": "duplicate_msg_id",
                        "msg_id": mid,
                        "agents": [seen_ids[mid], agent],
                    })
                else:
                    seen_ids[mid] = agent
            created = _parse_iso(m.get("created_at") or "")
            if created and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created and created < cutoff:
                anomalies.append({
                    "type": "stale_pending",
                    "agent": agent,
                    "msg_id": mid,
                    "created_at": m.get("created_at"),
                    "hours": int((datetime.now(timezone.utc) - created).total_seconds() // 3600),
                })
    return anomalies


def triage_inbox_anomaly(data_dir: str, config: dict | None = None) -> dict:
    """Scheduler job：扫描 + 通知调度。"""
    cfg_root = config or json_read(os.path.join(data_dir, "config.json"), {})
    llm_cfg = cfg_root.get("mailbus_internal_llm") or {}
    triggers = llm_cfg.get("triggers") or {}
    if not triggers.get("triage_inbox_anomaly", False):
        return {"status": "skipped", "reason": "trigger_disabled"}

    anomalies = scan_inbox_anomalies(data_dir)
    if not anomalies:
        return {"status": "ok", "anomalies": 0}

    stale = [a for a in anomalies if a["type"] == "stale_pending"]
    dupes = [a for a in anomalies if a["type"] == "duplicate_msg_id"]
    lines = [
        f"📥 Inbox triage · {len(anomalies)} 项异常",
        f"stale pending (>{_STALE_HOURS}h): {len(stale)}",
        f"duplicate msg_id: {len(dupes)}",
    ]
    for a in stale[:5]:
        lines.append(f"  · {a['agent']} {a.get('msg_id','?')} ~{a.get('hours')}h")
    for a in dupes[:3]:
        lines.append(f"  · dup {a.get('msg_id')} @ {','.join(a.get('agents') or [])}")

    summary = "\n".join(lines)
    _append_inbox_notice(
        data_dir,
        "xiaoqi",
        summary,
        msg_id=f"triage-inbox-{datetime.now(TZ_CN).strftime('%Y%m%d%H')}",
        no_llm=True,
    )
    return {"status": "ok", "anomalies": len(anomalies), "notified": "xiaoqi"}
