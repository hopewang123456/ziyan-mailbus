"""按 tier / task_type 提取 dispatch 动作约束。"""

from __future__ import annotations

from typing import Any, Dict


def dispatch_action_from_envelope(envelope: dict) -> Dict[str, Any]:
    action: Dict[str, Any] = {}
    tier = (envelope.get("tier") or "").strip()
    if tier:
        action["tier"] = tier.upper()
    task_type = envelope.get("task_type")
    if task_type:
        action["task_type"] = str(task_type).lower()
    constraints = envelope.get("constraints") or {}
    if isinstance(constraints.get("dispatch"), dict):
        action.update(constraints["dispatch"])
    ext = envelope.get("extensions") or {}
    ziyan = ext.get("mailbus") if isinstance(ext.get("mailbus"), dict) else {}
    disp = ziyan.get("dispatch") if isinstance(ziyan, dict) else {}
    if isinstance(disp, dict):
        action.update(disp)
    return action


def dispatch_action_from_step(planned_item: dict, envelope: dict) -> Dict[str, Any]:
    action: Dict[str, Any] = {}
    if planned_item.get("pin_agent"):
        action["pin_agent"] = planned_item["pin_agent"]
    if isinstance(planned_item.get("dispatch"), dict):
        action.update(planned_item["dispatch"])
    return action
