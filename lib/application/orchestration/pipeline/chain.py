"""pipeline 任务链初始化 — v3 planned_chain + Legacy 兼容。"""

from typing import Callable, List, Optional

from lib.application.orchestration.pipeline.step import is_pipeline_step as _is_pipeline_step
from lib.infra.agent_demo import pipeline_full_agents, pipeline_legacy_agent_role
from lib.infra.utils import _now_iso

# Legacy fallback：agent id → 角色名（仅当 role-types.json SoT 缺失时用 demo 名）
_LEGACY_AGENT_ROLE = pipeline_legacy_agent_role() or {
    "agent-a": "方案设计师",
    "agent-b": "调度员",
    "agent-c": "审查官",
    "agent-d": "开发工程师",
}

# Legacy fallback 全流程顺序（demo 名）
FULL_PIPELINE_AGENTS = pipeline_full_agents() or [
    "agent-a", "agent-b", "agent-d", "agent-c", "agent-b",
]


def _agent_role_map(data_dir: str = "") -> dict:
    """agent id → 角色中文名。SoT: role-types.json（store → team-pack → 公开 seed）。

    反向推导：遍历所有 role_type，candidates 中出现的 agent 映射到该角色。
    """
    from lib.infra.role_types import role_type_candidates, role_type_to_zh, valid_role_types

    out: dict[str, str] = {}
    for rt in valid_role_types(data_dir):
        zh = role_type_to_zh(rt, data_dir)
        for cand in role_type_candidates(rt, data_dir):
            out.setdefault(cand, zh)
    return out or dict(_LEGACY_AGENT_ROLE)


def agent_to_role(agent_id: str, data_dir: str = "") -> str:
    return _agent_role_map(data_dir).get(agent_id, _default_role_zh(data_dir))


def _default_role_zh(data_dir: str = "") -> str:
    """默认角色中文名：role-types.json 第一个角色，缺失时退回 demo。"""
    from lib.infra.role_types import role_type_to_zh, valid_role_types

    rts = valid_role_types(data_dir)
    if rts:
        return role_type_to_zh(rts[0], data_dir)
    zh = _LEGACY_AGENT_ROLE or {}
    return next(iter(zh.values()), "方案设计师")


def is_pipeline_step(item) -> bool:
    return _is_pipeline_step(item)


def _call_resolve_agent(resolve_agent, rt: int, pin, planned_item: dict):
    """兼容 resolve_agent(rt, pin) 与 resolve_agent(rt, pin, planned_item)。"""
    try:
        return resolve_agent(rt, pin, planned_item)
    except TypeError:
        return resolve_agent(rt, pin)


def init_chain_from_planned(
    planned_chain: List[dict],
    task_id: str,
    *,
    resolve_agent: Callable[..., tuple],
) -> List[dict]:
    """
    v3：planned_chain[0] → 首步 running；其余 → head.planned_role_types。
    resolve_agent(role_type, pin_agent, planned_item=None) -> (agent_id, dispatch_meta)
    dual_coding：若 planned[1].parallel_with=='dual'，同时创建 s2 并行步。
    """
    if not planned_chain:
        raise ValueError("empty planned_chain")

    first = planned_chain[0]
    rt0 = int(first["role_type"])
    pin0 = first.get("pin_agent")
    agent_id, meta = _call_resolve_agent(resolve_agent, rt0, pin0, first)

    rest_start = 1
    parallel_item = None
    if len(planned_chain) > 1 and planned_chain[1].get("parallel_with") == "dual":
        parallel_item = planned_chain[1]
        rest_start = 2

    rest = [int(x["role_type"]) for x in planned_chain[rest_start:]]

    step = {
        "step": 1,
        "step_id": "s1",
        "role_type": rt0,
        "to_agent": agent_id,
        "to_person": agent_id,
        "planned_role_types": rest,
        "dispatch_meta": meta,
        "status": "running",
        "fsm_state": "queued",
        "started_at": _now_iso(),
        "completed_at": None,
        "report": None,
        "result_consumed": False,
        "task_id": task_id,
        "result_ref": f"msg-results/{task_id}/step-s1.json",
    }
    if pin0:
        step["pin_agent"] = pin0
    if first.get("collab_mode"):
        step["collab_mode"] = first["collab_mode"]

    chain = [step]

    if parallel_item:
        rt1 = int(parallel_item["role_type"])
        pin1 = parallel_item.get("pin_agent")
        agent_id2, meta2 = _call_resolve_agent(resolve_agent, rt1, pin1, parallel_item)
        step2 = {
            "step": 2,
            "step_id": "s2",
            "role_type": rt1,
            "to_agent": agent_id2,
            "to_person": agent_id2,
            "dispatch_meta": meta2,
            "status": "running",
            "fsm_state": "queued",
            "started_at": _now_iso(),
            "completed_at": None,
            "report": None,
            "result_consumed": False,
            "task_id": task_id,
            "result_ref": f"msg-results/{task_id}/step-s2.json",
            "parallel_with": "s1",
        }
        if pin1:
            step2["pin_agent"] = pin1
        if parallel_item.get("collab_mode"):
            step2["collab_mode"] = parallel_item["collab_mode"]
        chain.append(step2)

    return chain


def init_first_step(agent_id: str, task_id: str = "") -> dict:
    role = agent_to_role(agent_id)
    return {
        "step": 1,
        "to_role": role,
        "to_person": agent_id,
        "action": f"等待{role}处理",
        "status": "running",
        "started_at": _now_iso(),
        "completed_at": None,
        "report": None,
        "task_id": task_id,
    }


def init_pipeline_chain(
    chain_hops: Optional[List],
    assignee: str,
    task_id: str = "",
) -> List[dict]:
    """Legacy API chain 规范化。"""
    if not chain_hops:
        return [init_first_step(assignee or "agent-a", task_id)]

    if is_pipeline_step(chain_hops[0]):
        return list(chain_hops)

    if all(isinstance(x, str) for x in chain_hops):
        first = chain_hops[0]
        step = init_first_step(first, task_id)
        if len(chain_hops) > 1:
            step["planned_agents"] = chain_hops[1:]
        return [step]

    return [init_first_step(assignee or "agent-a", task_id)]


def normalize_task_chain(task: dict) -> dict:
    """就地修复 legacy 任务的 chain 格式，返回 task。"""
    chain = task.get("chain") or []
    if not chain:
        assignee = task.get("assignee") or "agent-a"
        task["chain"] = [init_first_step(assignee, task.get("task_id", ""))]
        return task

    if is_pipeline_step(chain[0]):
        return task

    if all(isinstance(x, str) for x in chain):
        first = chain[0]
        task["chain"] = init_pipeline_chain(chain, first, task.get("task_id", ""))
        if task.get("status") == "pending":
            task["status"] = "running"
        return task

    return task
