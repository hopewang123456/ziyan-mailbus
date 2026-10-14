"""Wave 4 E6 — 工位注册表迁移：role-types + org_defaults → config.stations。

统一两套旧指派心智（role-types.json 候选表 + org_defaults 默认人）为
「工位」一等公民；幂等：已存在的工位不覆盖（--force 重建）。
schema 版本写 ``stations_version``，老 store 不迁移照常起（兼容 direct 模式）。
"""
from __future__ import annotations

import os
from typing import Any

from lib.infra.utils import json_read, json_write

STATIONS_VERSION = 1

# org_defaults 键 → 工位定义（description 为职责口径）
_ORG_STATIONS: dict[str, dict[str, Any]] = {
    "reviewer": {
        "title": "审核员",
        "description": "工单终审/复核：结论 approved / denied 的裁决人",
        "org_keys": ["reviewer"],
        "list_keys": ["audit_reviewers"],
    },
    "notify": {
        "title": "通知员",
        "description": "结论/异常通知的统一出口",
        "org_keys": [],
        "list_keys": ["notify_agents"],
    },
    "scheduler": {
        "title": "调度员",
        "description": "定时任务与巡检触发责任人",
        "org_keys": ["scheduler"],
        "list_keys": [],
    },
}


def _role_types_path(data_dir: str) -> str:
    return os.path.join(data_dir, "roles", "json", "role-types.json")


def derive_stations(data_dir: str) -> dict[str, dict[str, Any]]:
    """从 role-types + org_defaults 派生工位表（不写盘）。"""
    stations: dict[str, dict[str, Any]] = {}

    roles = (json_read(_role_types_path(data_dir), {}) or {}).get("roles") or {}
    for key, spec in roles.items():
        if not isinstance(spec, dict):
            continue
        try:
            rt = int(key)
        except (TypeError, ValueError):
            continue
        sid = str(spec.get("key") or f"role-{rt}")
        display = spec.get("display") or {}
        stations[sid] = {
            "title": display.get("zh") or sid,
            "description": f"{display.get('en') or sid}（源 role_type={rt}）",
            "candidates": [str(c) for c in (spec.get("candidates") or [])],
            "vacancy_policy": "adjudicate",
            "role_type": rt,
        }

    org = json_read(os.path.join(data_dir, "config.json"), {}).get("org_defaults") or {}
    for sid, spec in _ORG_STATIONS.items():
        candidates: list[str] = []
        for k in spec["org_keys"]:
            v = org.get(k)
            if isinstance(v, str) and v.strip():
                candidates.append(v.strip())
        for k in spec["list_keys"]:
            v = org.get(k)
            if isinstance(v, list):
                candidates.extend(str(x) for x in v if str(x).strip())
        # 保序去重（org reviewer 常与 audit_reviewers 重叠）
        candidates = list(dict.fromkeys(candidates))
        if not candidates:
            continue
        stations[sid] = {
            "title": spec["title"],
            "description": spec["description"],
            "candidates": candidates,
            "vacancy_policy": "adjudicate",
        }
    return stations


def migrate_stations(data_dir: str, *, force: bool = False) -> dict[str, Any]:
    cfg_path = os.path.join(data_dir, "config.json")
    cfg = json_read(cfg_path, {})
    existing = cfg.get("stations") if isinstance(cfg.get("stations"), dict) else {}
    derived = derive_stations(data_dir)

    created: list[str] = []
    updated: list[str] = []
    skipped: list[str] = []
    for sid, st in derived.items():
        if sid in existing and not force:
            skipped.append(sid)
            continue
        if sid in existing:
            updated.append(sid)
        else:
            created.append(sid)
        existing[sid] = st

    cfg["stations"] = existing
    cfg["stations_version"] = STATIONS_VERSION
    json_write(cfg_path, cfg)
    return {
        "created": created,
        "updated": updated,
        "skipped_preserved": skipped,
        "total": len(existing),
        "version": STATIONS_VERSION,
    }
