"""role_type → agent 解析（pin > 负载感知空闲优先 > round-robin 兜底）。"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Set, Tuple

from lib.composition import get_locale
from lib.infra.utils import json_read, json_write, resolve_paths

_ACTIVE_TASK_STATUSES = {"running", "pending", "blocked"}
_TERMINAL_STEP_STATES = {"completed", "skipped", "superseded"}
_DEFAULT_CONCURRENCY = 1


def _agent_dispatchable(data_dir: str, agent: str, agents_cfg: dict) -> bool:
    if not agent:
        return False
    if agent in agents_cfg:
        if agents_cfg[agent].get("available") is False:
            return False
        return True
    paths = resolve_paths(data_dir)
    return os.path.isdir(os.path.join(paths["inbox"], agent))


def _active_load(data_dir: str) -> Dict[str, int]:
    """每个 agent 当前占用数（活跃任务/步骤）。失败时静默回退空表。"""
    try:
        from lib.application.orchestration.tracker import TaskTracker

        tracker = TaskTracker(data_dir)
        counts: Dict[str, int] = {}
        for task in tracker.list_all():
            if task.get("status") not in _ACTIVE_TASK_STATUSES:
                continue
            assignee = task.get("assignee") or ""
            if assignee and assignee not in counts:
                counts[assignee] = 0
            chain = task.get("chain") or []
            touched = set()
            for step in chain:
                to_agent = step.get("to_agent") or step.get("to_person") or ""
                step_state = step.get("fsm_state") or step.get("status") or ""
                if to_agent and step_state not in _TERMINAL_STEP_STATES:
                    touched.add(to_agent)
            if not touched and assignee:
                touched.add(assignee)
            for agent in touched:
                counts[agent] = counts.get(agent, 0) + 1
        return counts
    except Exception:
        return {}


def _busy_agents(
    data_dir: str,
    agents_cfg: dict,
    active: Dict[str, int],
    default_concurrency: int,
) -> Set[str]:
    busy: Set[str] = set()
    for agent in agents_cfg:
        limit = int((agents_cfg[agent] or {}).get("concurrency") or default_concurrency)
        if limit <= 0:
            continue
        if active.get(agent, 0) >= limit:
            busy.add(agent)
    return busy


def _pick_round_robin(data_dir: str, role_type: int, candidates: List[str]) -> Tuple[str, dict]:
    rr_path = os.path.join(data_dir, "dispatch", "role-round-robin.json")
    rr = json_read(rr_path, {"version": "1.0.0", "cursors": {}})
    cursors = rr.setdefault("cursors", {})
    key = str(int(role_type))
    if not candidates:
        return "", {"error": "no_candidate", "role_type": role_type}
    idx = int(cursors.get(key, 0)) % len(candidates)
    agent = candidates[idx]
    cursors[key] = idx + 1
    os.makedirs(os.path.dirname(rr_path), exist_ok=True)
    json_write(rr_path, rr)
    return agent, {
        "source": "round_robin",
        "role_type": int(role_type),
        "candidates": candidates,
        "index": idx,
    }


def role_type_candidates(role_type: int, data_dir: str = "") -> List[str]:
    """Compat wrapper — prefer LocalePort via composition."""
    return list(get_locale(data_dir).role_type_candidates(int(role_type)))


def _dispatch_config(data_dir: str, agents_cfg: dict) -> Tuple[bool, int]:
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    dispatch_cfg = cfg.get("dispatch") or {}
    load_aware = bool(dispatch_cfg.get("load_aware", True))
    default_concurrency = int(dispatch_cfg.get("default_concurrency") or _DEFAULT_CONCURRENCY)
    return load_aware, default_concurrency


def resolve_agent_for_role_type(
    data_dir: str,
    role_type: int,
    *,
    pin_agent: Optional[str] = None,
    exclude: Optional[Set[str] | List[str]] = None,
    action: Optional[dict] = None,
    agents_cfg: Optional[dict] = None,
) -> Tuple[str, Dict[str, Any]]:
    if agents_cfg is None:
        agents_cfg = json_read(os.path.join(data_dir, "config.json"), {}).get("agents") or {}

    excluded: Set[str] = set(exclude or [])
    act = action or {}

    for pin in (pin_agent, act.get("pin_agent")):
        if pin and pin not in excluded and _agent_dispatchable(data_dir, pin, agents_cfg):
            return pin, {"source": "pin", "role_type": int(role_type), "agent": pin}

    cands = get_locale(data_dir).role_type_candidates(int(role_type))
    dispatchable = [
        c for c in cands
        if c not in excluded and _agent_dispatchable(data_dir, c, agents_cfg)
    ]
    pool = dispatchable or [c for c in cands if c not in excluded]

    load_aware, default_concurrency = _dispatch_config(data_dir, agents_cfg)
    if load_aware and dispatchable:
        active = _active_load(data_dir)
        busy = _busy_agents(data_dir, agents_cfg, active, default_concurrency)
        idle = [c for c in dispatchable if c not in busy]
        if idle:
            # 候选顺序即“适配度”顺序：取最靠前且空闲的员工；全员忙才轮询
            return idle[0], {
                "source": "idle_first",
                "role_type": int(role_type),
                "agent": idle[0],
                "candidates": list(cands),
                "skipped_busy": [c for c in dispatchable if c in busy],
                "load": active.get(idle[0], 0),
            }
    return _pick_round_robin(data_dir, int(role_type), pool)

