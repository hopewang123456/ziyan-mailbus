"""Agent 在线/离线状态 — 供派发 forbidden 与 failover 使用。"""

from __future__ import annotations

import os
from typing import Set

from ..utils import json_read

OFFLINE_MISSED_THRESHOLD = 3


def get_offline_agents(data_dir: str, *, missed_threshold: int = OFFLINE_MISSED_THRESHOLD) -> Set[str]:
    """连续 missed_pings >= threshold 且 status=offline 的 agent。"""
    hb_path = os.path.join(data_dir, "heartbeat.json")
    hb = json_read(hb_path, {})
    statuses = hb.get("agents") or {}
    offline: Set[str] = set()
    for name, info in statuses.items():
        if not isinstance(info, dict):
            continue
        if info.get("status") != "offline":
            continue
        missed = int(info.get("missed_pings") or 0)
        if missed >= missed_threshold:
            offline.add(name)
    return offline


def is_agent_offline(data_dir: str, agent_id: str) -> bool:
    return agent_id in get_offline_agents(data_dir)
