"""pipeline 任务链初始化 — v3 planned_chain + Legacy 兼容。"""

from typing import Callable, List, Optional

from lib.application.orchestration.pipeline.step import is_pipeline_step as _is_pipeline_step
from lib.infra.utils import _now_iso

# agent id → 角色名（Legacy push 展示 · 迁移脚本用）
AGENT_ROLE = {
    "lingzhao": "方案设计师",
    "xiaoqi": "调度员",
    "lingxiao": "开发工程师",
    "dali": "开发工程师",
    "lingjian": "审查官",
    "lingyun": "开发工程师",
    "lingyan": "测试工程师",
    "lingjin": "安全审计师",
    "lingxi": "技术研究员",
    "lingxun": "巡检官",
    "lingtuo": "市场拓展官",
    "lingzhang": "财务跟进官",
    "yige": "运营",
}

FULL_PIPELINE_AGENTS = [
    "lingzhao", "xiaoqi", "lingxiao", "lingjian", "lingyan", "xiaoqi",
]


def agent_to_role(agent_id: str) -> str:
    return AGENT_ROLE.get(agent_id, "方案设计师")


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
        return [init_first_step(assignee or "lingzhao", task_id)]

    if is_pipeline_step(chain_hops[0]):
        return list(chain_hops)

    if all(isinstance(x, str) for x in chain_hops):
        first = chain_hops[0]
        step = init_first_step(first, task_id)
        if len(chain_hops) > 1:
            step["planned_agents"] = chain_hops[1:]
        return [step]

    return [init_first_step(assignee or "lingzhao", task_id)]


def normalize_task_chain(task: dict) -> dict:
    """就地修复 legacy 任务的 chain 格式，返回 task。"""
    chain = task.get("chain") or []
    if not chain:
        assignee = task.get("assignee") or "lingzhao"
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
