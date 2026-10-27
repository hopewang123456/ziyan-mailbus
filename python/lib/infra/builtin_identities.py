"""内置身份 SoT — D2/D15（P1 二期）：子言=第一内置主仓角色，清单可枚举扩展。

优先级：
  1. ``{data_dir}/config/builtin-identities.json``（用户侧改名落此；其余字段继承 seed）
  2. ``MAILBUS_ROOT/config/mailbus/builtin-identities.json``（代码仓 seed，随产品分发）

身份 ``id`` 稳定不可改（历史引用不断链）；``display_name`` 可编辑（D2）。
本期不做权限体系（D15）；新内置身份 = 往 seed/覆盖文件清单里加条目。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from lib.infra.constants import MAILBUS_ROOT
from lib.infra.utils import json_read, json_write

_SEED_PATH = os.path.join(str(MAILBUS_ROOT), "config", "mailbus", "builtin-identities.json")


def _seed_doc() -> dict:
    return json_read(_SEED_PATH, {"identities": []})


def _override_path(data_dir: str) -> str:
    return os.path.join(data_dir, "config", "builtin-identities.json")


def load_builtin_identities(data_dir: str = "") -> List[Dict[str, Any]]:
    """合并 seed 与用户覆盖（display_name 等字段覆盖，id/role 以 seed 为锚）。"""
    seed = _seed_doc().get("identities") or []
    by_id = {str(e.get("id")): dict(e) for e in seed if e.get("id")}
    if data_dir:
        ov = json_read(_override_path(data_dir), {}).get("identities") or []
        for e in ov:
            eid = str(e.get("id") or "")
            if eid in by_id:
                by_id[eid].update({k: v for k, v in e.items() if k != "id"})
    return list(by_id.values())


def merge_into_agents(agents: Dict[str, Any], data_dir: str = "") -> Dict[str, Any]:
    """把内置身份注入 agents 运行时视图（不写回 config.json）。

    注入后 send_msg / inbox / /api/agents 等既有机制对内置身份即刻生效。
    """
    for ident in load_builtin_identities(data_dir):
        iid = str(ident.get("id") or "")
        if not iid:
            continue
        entry = agents.get(iid) or {}
        entry.setdefault("name", ident.get("display_name") or iid)
        entry.setdefault("type", "builtin")
        entry.setdefault("role", ident.get("role") or "")
        entry.setdefault("available", True)
        entry["builtin"] = True
        agents[iid] = entry
    return agents


def rename_identity(data_dir: str, ident_id: str, display_name: str) -> Dict[str, Any] | None:
    """改 display_name（D2 改名按钮后端）；写覆盖文件，id 与 role 不动。"""
    display_name = (display_name or "").strip()
    if not display_name:
        return None
    seed_ids = {str(e.get("id")) for e in _seed_doc().get("identities") or []}
    if ident_id not in seed_ids:
        return None
    path = _override_path(data_dir)
    doc = json_read(path, {"identities": []})
    entries = {(e.get("id") or ""): e for e in (doc.get("identities") or [])}
    entry = entries.get(ident_id) or {"id": ident_id}
    entry["display_name"] = display_name
    entries[ident_id] = entry
    doc["identities"] = list(entries.values())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json_write(path, doc)
    for e in load_builtin_identities(data_dir):
        if str(e.get("id")) == ident_id:
            return e
    return None
