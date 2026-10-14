"""Pipeline step 字段访问与 planned 队列 — domain 级纯函数。

原位置 `lib/application/orchestration/pipeline/step.py`（2026-09 治理下沉）。
这些函数都是 dict 字段提取 / 列表遍历，无 I/O、无副作用、无 application 子树依赖，
适合放在 domain 层。新代码请直接 import `lib.domain.pipeline_step`；
旧路径保留 compat shim。

依赖注意：`step_role_zh` 在 agent 名查不到 role 时 lazy import chain._agent_role_map —
那是「带运行时配置的回退」，仍走 compat 路径调用 application 子树（domain → application
不允许，所以放回 application/orchestration/pipeline/step.py 里的兼容 wrapper 处理）。
"""
from __future__ import annotations

from typing import Any, List


_ROLE_TYPE_ZH = {
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


def is_pipeline_step(item: Any) -> bool:
    return isinstance(item, dict) and bool(item.get("step_id") or item.get("to_agent") or item.get("to_person"))


def is_role_pipeline_task(task: dict) -> bool:
    """True when chain head carries role_type / planned_role_types (current pipeline schema)."""
    chain = task.get("chain") or []
    if not chain or not isinstance(chain[0], dict):
        return False
    head = chain[0]
    return bool(head.get("planned_role_types") is not None or head.get("role_type") is not None)


def step_agent(step: dict) -> str:
    return (step.get("to_agent") or step.get("to_person") or "").strip()


def step_role_type(step: dict) -> int:
    rt = step.get("role_type")
    if rt is not None:
        return int(rt)
    role = step.get("to_role") or ""
    for k, zh in _ROLE_TYPE_ZH.items():
        if zh == role:
            return k
    return 0


def planned_agents_remaining(chain: List[dict]) -> List[str]:
    head = chain[0] if chain else {}
    planned = head.get("planned_agents")
    return list(planned) if isinstance(planned, list) else []


def planned_role_types_remaining(chain: List[dict]) -> List[int]:
    head = chain[0] if chain else {}
    planned = head.get("planned_role_types")
    if isinstance(planned, list):
        return [int(x) for x in planned]
    return []


__all__ = [
    "is_pipeline_step",
    "is_role_pipeline_task",
    "step_agent",
    "step_role_type",
    "planned_agents_remaining",
    "planned_role_types_remaining",
]