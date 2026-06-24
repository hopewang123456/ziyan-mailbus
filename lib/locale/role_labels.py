"""Push 展示层 — role_type int → 中文标签。"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict, Optional

from ..utils import json_read


def _role_types_path(data_dir: Optional[str] = None) -> str:
    base = data_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "store",
    )
    return os.path.join(base, "roles", "json", "role-types.json")


@lru_cache(maxsize=4)
def _load_role_types_cached(path: str) -> Dict[int, dict]:
    data = json_read(path, {})
    roles = data.get("roles") or {}
    out: Dict[int, dict] = {}
    for k, v in roles.items():
        try:
            out[int(k)] = v
        except (TypeError, ValueError):
            continue
    return out


def load_role_types(data_dir: Optional[str] = None) -> Dict[int, dict]:
    return _load_role_types_cached(_role_types_path(data_dir))


def role_type_to_zh(role_type: int, data_dir: Optional[str] = None) -> str:
    info = load_role_types(data_dir).get(int(role_type), {})
    display = info.get("display") or {}
    return display.get("zh") or info.get("key") or str(role_type)


def role_type_candidates(role_type: int, data_dir: Optional[str] = None) -> list:
    info = load_role_types(data_dir).get(int(role_type), {})
    return list(info.get("candidates") or [])


def zh_to_role_type(zh: str, data_dir: Optional[str] = None) -> Optional[int]:
    for rt, info in load_role_types(data_dir).items():
        if (info.get("display") or {}).get("zh") == zh:
            return rt
    return None


def valid_role_types(data_dir: Optional[str] = None) -> frozenset:
    return frozenset(load_role_types(data_dir).keys())
