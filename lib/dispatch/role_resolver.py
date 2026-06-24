"""按 role_type load+RR 解析 agent。"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Set, Tuple

from ..locale.role_labels import load_role_types, role_type_candidates
from ..utils import json_read, json_write
from .agent_availability import get_offline_agents
from .tier_filter import filter_candidates_by_tier


def _rr_path(data_dir: str) -> str:
    return os.path.join(data_dir, "dispatch", "role-round-robin.json")


def _roster_path(data_dir: str) -> str:
    return os.path.join(data_dir, "roles", "json", "roster.json")


def _agent_loads(data_dir: str, candidates: List[str]) -> Dict[str, int]:
    """统计 executing/running task 中各 agent 活跃步数（近似 load）。"""
    tasks_dir = os.path.join(data_dir, "tasks")
    loads = {c: 0 for c in candidates}
    if not os.path.isdir(tasks_dir):
        return loads
    for name in os.listdir(tasks_dir):
        if not name.endswith(".json"):
            continue
        task = json_read(os.path.join(tasks_dir, name), {})
        if (task.get("status") or "") not in ("running", "pending"):
            fsm = task.get("fsm") or {}
            if fsm.get("state") not in ("executing", "created", "accepting", "blocked"):
                continue
        assignee = task.get("assignee") or ""
        if assignee in loads:
            loads[assignee] += 1
    return loads


def _pick_rr(data_dir: str, role_type: int, candidates: List[str]) -> str:
    if len(candidates) == 1:
        return candidates[0]
    rr_file = _rr_path(data_dir)
    rr = json_read(rr_file, {"cursors": {}})
    cursors = rr.setdefault("cursors", {})
    key = str(role_type)
    idx = int(cursors.get(key, 0)) % len(candidates)
    chosen = candidates[idx]
    cursors[key] = (idx + 1) % len(candidates)
    rr["cursors"] = cursors
    os.makedirs(os.path.dirname(rr_file), exist_ok=True)
    json_write(rr_file, rr)
    return chosen


def resolve_agent_for_role_type(
    data_dir: str,
    role_type: int,
    *,
    exclude: Optional[Set[str]] = None,
    pin_agent: Optional[str] = None,
    forbidden: Optional[Set[str]] = None,
    action: Optional[dict] = None,
    agents_cfg: Optional[dict] = None,
) -> Tuple[str, dict]:
    """
    返回 (agent_id, dispatch_meta)。
    pin_agent 优先；否则 tier 过滤 + least_load + RR 平局打破。
    forbidden 默认含 offline agent（heartbeat）。
    """
    rt = int(role_type)
    skip = exclude or set()
    banned = forbidden if forbidden is not None else get_offline_agents(data_dir)
    if agents_cfg is None:
        agents_cfg = json_read(os.path.join(data_dir, "config.json"), {}).get("agents") or {}

    base_candidates = role_type_candidates(rt, data_dir)
    tier_filtered = filter_candidates_by_tier(rt, base_candidates, action, agents_cfg)
    candidates = [
        c for c in tier_filtered
        if c not in skip and c not in banned
    ]
    if not candidates:
        candidates = [c for c in tier_filtered if c not in skip]
    if not candidates:
        candidates = [c for c in base_candidates if c not in skip and c not in banned]
    if not candidates:
        candidates = base_candidates

    if pin_agent and pin_agent in candidates:
        agent_id = pin_agent
        method = "pin_agent"
    elif pin_agent and pin_agent not in banned:
        agent_id = pin_agent
        method = "pin_agent_forced"
    else:
        loads = _agent_loads(data_dir, candidates)
        min_load = min(loads.get(c, 0) for c in candidates)
        tied = [c for c in candidates if loads.get(c, 0) == min_load]
        agent_id = _pick_rr(data_dir, rt, tied)
        method = "least_load+rr"

    loads = _agent_loads(data_dir, candidates)
    meta = {
        "method": method,
        "candidates": candidates,
        "tier_filtered": tier_filtered,
        "loads": {c: loads.get(c, 0) for c in candidates},
        "role_type": rt,
        "forbidden": sorted(banned),
        "action": action or {},
    }
    return agent_id, meta


def agents_for_role_type(data_dir: str, role_type: int) -> List[str]:
    roster = json_read(_roster_path(data_dir), {})
    rt = int(role_type)
    found = []
    for m in roster.get("members") or []:
        types = m.get("role_types") or []
        if rt in types:
            found.append(m.get("id"))
    if found:
        return found
    return role_type_candidates(rt, data_dir)
