"""role_type 整数 ↔ 中文角色名 — SoT: role-types.json（store → team-pack → 公开 seed）。

本模块是 LocalePort 的 role 适配器；核心逻辑在 lib.infra.role_types（application 也依赖）。
"""
from __future__ import annotations

from typing import List

from lib.infra.role_types import (
    role_type_candidates as _role_type_candidates,
    role_type_to_zh as _role_type_to_zh,
    valid_role_types as _valid_role_types,
    zh_to_role_type as _zh_to_role_type,
)


def role_type_to_zh(role_type: int, data_dir: str = "") -> str:
    return _role_type_to_zh(int(role_type), data_dir)


def zh_to_role_type(role_zh: str, data_dir: str = "") -> int:
    return _zh_to_role_type(role_zh, data_dir)


def role_type_candidates(role_type: int, data_dir: str = "") -> List[str]:
    return _role_type_candidates(int(role_type), data_dir)


def valid_role_types(data_dir: str = "") -> List[int]:
    return _valid_role_types(data_dir)
