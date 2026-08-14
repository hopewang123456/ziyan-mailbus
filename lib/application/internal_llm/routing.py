"""自动中转路由提示词草案（选「下一棒」agent）。

设计契约（本版交付；工单字段/状态机留待下一 session 定稿）：
- 输入：任务摘要 + 名册（agent_id / role / skills / status）
- 输出：下一 `agent_id` + reason + confidence + disposition
- 硬约束：**禁止输出 transport**（A2A/file_bus 由总线按接收方配置决定，本层不可见）
- 无合适人选：`next_agent_id=null` + `disposition=human|hold`（升级人类 / 挂起）

本模块只提供 prompt 常量 + 组装/解析纯函数，不接入真实调度循环；
接入点在下 session 与工单流转细则一起落地。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Set

ROUTING_SYSTEM_PROMPT = (
    "You are the mailbus routing planner. Given a task and an agent roster, "
    "choose the SINGLE next agent to handle this hop.\n"
    "Output ONLY valid JSON:\n"
    '{"next_agent_id": "<agent_id|null>", "reason": "<short reason>", '
    '"confidence": <0-1>, "disposition": "<dispatch|human|hold>"}\n'
    "Rules:\n"
    "- Pick the agent whose role/skills best match the task and who is available.\n"
    "- Do NOT output transport (A2A/file_bus) — the bus chooses it per receiver config.\n"
    "- If no suitable agent: next_agent_id=null, disposition=human (escalate) or hold.\n"
    "- reason <= 120 chars; explain why this agent fits.\n"
    "- Never invent an agent_id absent from the roster."
)


def build_routing_prompt(
    task_summary: str,
    roster: List[Dict[str, Any]],
    *,
    hints: str = "",
) -> str:
    """组装 user prompt：任务摘要 + 名册（role/skills/status）。"""
    lines = [f"TASK: {task_summary}"]
    if hints:
        lines.append(f"HINTS: {hints}")
    lines.append("ROSTER:")
    for a in roster:
        agent_id = a.get("agent_id") or a.get("id") or "?"
        role = a.get("role") or a.get("role_zh") or a.get("role_type") or "-"
        status = a.get("status") or "available"
        skills = a.get("skills") or []
        if isinstance(skills, (list, tuple)):
            skills = ",".join(str(s) for s in skills)
        lines.append(f"- {agent_id} | role={role} | status={status} | skills={skills}")
    return "\n".join(lines)


def parse_routing_output(raw: str, roster_ids: Set[str]) -> Dict[str, Any]:
    """解析并校验 LLM 返回的下一棒。

    非法/幻觉 agent_id → 视为无合适人选，落 disposition=human；
    未显式指定 disposition 时按结果兜底推导，避免调度层拿到矛盾状态。
    """
    try:
        data = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except (json.JSONDecodeError, TypeError):
        return {
            "next_agent_id": None,
            "reason": "unparseable output",
            "confidence": 0.0,
            "disposition": "human",
        }

    nid = data.get("next_agent_id")
    if nid and nid not in roster_ids:
        nid = None

    disposition = data.get("disposition")
    if nid is None and disposition not in ("human", "hold"):
        disposition = "human"
    elif nid and disposition != "dispatch":
        disposition = "dispatch"

    return {
        "next_agent_id": nid,
        "reason": (data.get("reason") or "")[:120],
        "confidence": float(data.get("confidence") or 0.0),
        "disposition": disposition,
    }
