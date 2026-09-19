"""Wave 4 工位模型 — 工位注册表读取、在岗解析、空缺进待裁决。

D3 语义：
- 工位 = {title, description, candidates(有序), vacancy_policy}，
  注册表 SoT 在 store/config.json 的 ``stations`` 段（E6 迁移工具生成）；
- 派工解析：工单 → 工位 → 在岗角色（按序取首个可用）；全空缺 →
  任务 blocked + 待裁决队列（改派/临时指名/挂起），**零 token**——不尝试投递；
- 审计：step 同时留 ``station``（工位）与 ``to_agent``（最终人）；
- 兼容：直接指名 agent（pin/planned_agents）与 role_type 老路径不受影响。
"""
from __future__ import annotations

import os
from typing import Any, Optional

from lib.infra.utils import json_read

_STATIONS_VERSION = 1


def station_registry(data_dir: str) -> dict[str, dict[str, Any]]:
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    stations = cfg.get("stations")
    return stations if isinstance(stations, dict) else {}


def station_role_type(data_dir: str, station_id: str) -> Optional[int]:
    st = station_registry(data_dir).get(station_id) or {}
    try:
        return int(st["role_type"]) if st.get("role_type") is not None else None
    except (TypeError, ValueError):
        return None


def _candidate_available(agents_cfg: dict, agent_id: str) -> bool:
    cfg = agents_cfg.get(agent_id)
    if not isinstance(cfg, dict):
        return False
    if cfg.get("enabled") is False:
        return False
    if cfg.get("available") is False:
        return False
    return True


def resolve_agent_for_station(
    data_dir: str,
    station_id: str,
    *,
    exclude: Optional[set[str] | list[str]] = None,
    agents_cfg: Optional[dict] = None,
) -> tuple[str, dict[str, Any]]:
    """工位 → 在岗角色（按序首个可用）。空缺返回 ("", {vacancy: ...})。

    vacancy_policy:
      - adjudicate（默认）：空缺交由调用方进待裁决队列；
      - reject：直接空，调用方按普通 no_assignee 处理。
    """
    if agents_cfg is None:
        agents_cfg = json_read(os.path.join(data_dir, "config.json"), {}).get("agents") or {}
    st = station_registry(data_dir).get(station_id)
    if not isinstance(st, dict):
        return "", {"error": "unknown_station", "station": station_id}
    candidates = [str(c) for c in (st.get("candidates") or []) if str(c).strip()]
    excluded = set(exclude or [])
    for cand in candidates:
        if cand in excluded:
            continue
        if _candidate_available(agents_cfg, cand):
            return cand, {
                "source": "station",
                "station": station_id,
                "agent": cand,
                "candidates": candidates,
            }
    return "", {
        "vacancy": True,
        "station": station_id,
        "candidates": candidates,
        "policy": st.get("vacancy_policy") or "adjudicate",
        "reason": "station_vacant",
    }


def station_vacancy_blocked(task: dict, data_dir: str, station_id: str, *, candidates: Optional[list] = None) -> bool:
    """空缺动作：任务 blocked + 待裁决队列（source=station_vacancy），零 token。"""
    from lib.domain.fsm import TaskFsmState
    from lib.infra.mbus_log import warn
    from lib.infra.utils import _now_iso

    fsm = task.setdefault("fsm", {})
    fsm["state"] = TaskFsmState.BLOCKED.value
    fsm["reason"] = f"station_vacant:{station_id}"
    task["status"] = "blocked"
    tid = task.get("task_id") or task.get("id") or ""
    try:
        # 跨层解耦：application→composition 服务
        from lib.composition import enqueue_human_queue

        enqueue_human_queue(data_dir, {
            "type": "station_vacancy",
            "title": f"工位空缺：{station_id}",
            "source": "station_vacancy",
            "task_id": tid,
            "station": station_id,
            "reason": (
                f"工位「{station_id}」全空缺（候选：{', '.join(candidates or []) or '未配置'}）——"
                "工单已暂停且未产生任何投递/token 消耗。请裁决：改派其他工位 / 临时指名 / 补员后重推"
            ),
            "severity": "warn",
            "ts": _now_iso(),
        })
    except Exception:
        pass
    warn(f"[station] vacant {station_id} task={str(tid)[:24]} -> blocked (adjudicate)")
    return True
