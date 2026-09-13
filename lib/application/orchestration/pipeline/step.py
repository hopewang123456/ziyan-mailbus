"""Compat shim — 纯函数已下沉到 `lib.domain.pipeline_step`。

`step_role_zh` 需要 chain._agent_role_map（agent 名 → 角色中文），该回退路径依赖
application 子树，所以保留在本文件。新代码请直接 import `lib.domain.pipeline_step`。
"""
from lib.domain.pipeline_step import (  # noqa: F401
    is_pipeline_step,
    is_role_pipeline_task,
    step_agent,
    step_role_type,
    planned_agents_remaining,
    planned_role_types_remaining,
)


def step_role_zh(step: dict, data_dir: str = "") -> str:
    """带运行时配置回退的角色名查找。

    优先取 step['to_role']，否则按 role_type 映射，否则按 agent 名查 chain 表。
    chain._agent_role_map 需要 application 子树上下文，故保留在 application 层。
    """
    role = step.get("to_role")
    if role:
        return role
    rt = step.get("role_type")
    if rt is not None:
        from lib.domain.pipeline_step import _ROLE_TYPE_ZH
        return _ROLE_TYPE_ZH.get(int(rt), "方案设计师")
    agent = step_agent(step)
    if not agent:
        return "方案设计师"
    from lib.application.orchestration.pipeline.chain import _agent_role_map

    return _agent_role_map(data_dir).get(agent, "方案设计师")


__all__ = [
    "is_pipeline_step",
    "is_role_pipeline_task",
    "step_agent",
    "step_role_type",
    "step_role_zh",
    "planned_agents_remaining",
    "planned_role_types_remaining",
]