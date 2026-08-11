"""role_type 整数 ↔ 中文角色名 — SoT: team-pack/org/json/role-types.json。"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

from lib.infra.constants import TEAM_PACK_ROOT
from lib.infra.utils import json_read

_ZH_FALLBACK = {
    1: "方案设计师",
    2: "安全审计师",
    3: "技术研究员",
    4: "市场拓展官",
    5: "审查官",
    6: "测试工程师",
    7: "巡检官",
    8: "开发工程师",
    9: "调度员",
    10: "财务跟进官",
    11: "运营",
    12: "验收员",
}


@lru_cache(maxsize=4)
def _load_role_types(path: str) -> dict:
    doc = json_read(path, {})
    return doc.get("roles") or {}


def _roles_sot(data_dir: str = "") -> dict:
    candidates = []
    if data_dir:
        candidates.append(os.path.join(data_dir, "roles", "json", "role-types.json"))
    candidates.append(str(TEAM_PACK_ROOT / "org" / "json" / "role-types.json"))
    for path in candidates:
        if os.path.isfile(path):
            return _load_role_types(path)
    return {}


def role_type_to_zh(role_type: int, data_dir: str = "") -> str:
    roles = _roles_sot(data_dir)
    entry = roles.get(str(int(role_type))) or {}
    disp = entry.get("display") or {}
    return disp.get("zh") or _ZH_FALLBACK.get(int(role_type), "方案设计师")


def zh_to_role_type(role_zh: str, data_dir: str = "") -> int:
    roles = _roles_sot(data_dir)
    for key, entry in roles.items():
        disp = (entry or {}).get("display") or {}
        if disp.get("zh") == role_zh:
            return int(key)
    for rt, zh in _ZH_FALLBACK.items():
        if zh == role_zh:
            return rt
    return 0


def role_type_candidates(role_type: int, data_dir: str = "") -> List[str]:
    roles = _roles_sot(data_dir)
    entry = roles.get(str(int(role_type))) or {}
    cands = entry.get("candidates")
    return list(cands) if isinstance(cands, list) else []


def valid_role_types(data_dir: str = "") -> List[int]:
    roles = _roles_sot(data_dir)
    out: List[int] = []
    for key in roles:
        try:
            out.append(int(key))
        except (TypeError, ValueError):
            continue
    return sorted(out) or sorted(_ZH_FALLBACK.keys())
