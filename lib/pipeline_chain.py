"""pipeline 任务链初始化与 legacy chain 格式兼容。"""

from typing import List, Optional
from .utils import _now_iso

# agent id → 角色名（与 role-flow-config.md / role_flow.py 一致）
AGENT_ROLE = {
    "lingzhao": "方案设计师",
    "xiaoqi": "调度员",
    "lingxiao": "开发工程师",
    "dali": "开发工程师",
    "lingjian": "审查官",
    "lingyan": "测试工程师",
    "lingjin": "安全审计师",
    "lingxi": "技术研究员",
    "lingxun": "巡检官",
    "yige": "运营",
}

# 标准完整流水线 agent 顺序（供 API template=full 使用）
FULL_PIPELINE_AGENTS = [
    "lingzhao", "xiaoqi", "lingxiao", "lingjian", "lingyan", "xiaoqi",
]


def agent_to_role(agent_id: str) -> str:
    return AGENT_ROLE.get(agent_id, "方案设计师")


def is_pipeline_step(item) -> bool:
    return isinstance(item, dict) and item.get("to_person")


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
    """
    将 API 传入的 chain 规范化为 pipeline 步骤对象列表。

    - None / [] → 按 assignee 初始化第一步
    - ["lingzhao", "xiaoqi", ...] → 第一步 running，其余存 planned_agents
    - [{to_person, to_role, ...}] → 原样返回（已是 pipeline 格式）
    """
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
