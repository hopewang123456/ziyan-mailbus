"""Inbox 异常巡检（scheduler triage-inbox job）。"""

from __future__ import annotations

import os
from typing import Any

from lib.infra.utils import json_read, resolve_paths


def triage_inbox_anomaly(data_dir: str, config: dict | None = None) -> dict[str, Any]:
    """
    扫描全员 inbox，统计 pending 过久 / pushed_count=0 等简单异常。
    仅报告，不自动修复。
    """
    cfg = config or json_read(os.path.join(data_dir, "config.json"), {})
    agents = (cfg.get("agents") or {}).keys()
    paths = resolve_paths(data_dir)
    anomalies: list[dict[str, Any]] = []

    for name in agents:
        inbox_file = f"{paths['inbox']}/{name}/inbox.json"
        inbox_data = json_read(inbox_file, {})
        if not inbox_data:
            continue
        for m in inbox_data.get("messages") or []:
            if not isinstance(m, dict):
                continue
            status = (m.get("status") or m.get("state") or "").lower()
            if status != "pending":
                continue
            pushed = int(m.get("pushed_count") or 0)
            if pushed == 0:
                anomalies.append({
                    "agent": name,
                    "msg_id": m.get("id", ""),
                    "kind": "pending_never_pushed",
                })

    return {
        "status": "ok",
        "anomalies": len(anomalies),
        "items": anomalies[:50],
    }
