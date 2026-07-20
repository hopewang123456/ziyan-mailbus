"""role_type → agent 解析（round-robin + pin）。"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Set, Tuple

from ..locale.role_labels import role_type_candidates
from ..utils import json_read, json_write, resolve_paths


def _agent_dispatchable(data_dir: str, agent: str, agents_cfg: dict) -> bool:
    if not agent:
        return False
    if agent in agents_cfg:
        if agents_cfg[agent].get("available") is False:
            return False
        return True
    paths = resolve_paths(data_dir)
    return os.path.isdir(os.path.join(paths["inbox"], agent))


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

    cands = role_type_candidates(int(role_type), data_dir)
    available = [
        c for c in cands
        if c not in excluded and _agent_dispatchable(data_dir, c, agents_cfg)
    ]
    if not available:
        available = [c for c in cands if c not in excluded]
    return _pick_round_robin(data_dir, int(role_type), available)
