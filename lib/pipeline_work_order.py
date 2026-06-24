"""Pipeline 步骤工单元数据（msg-files/*.md）。"""

from __future__ import annotations

import os
from typing import Optional

from .pipeline_chain import agent_to_role
from .utils import generate_msg_id


def write_pipeline_work_order(
    data_dir: str,
    *,
    task_id: str,
    step_num: int,
    to_person: str,
    to_role: str,
    from_person: str = "mailbus",
    from_role: str = "调度",
    summary: str = "",
    planned_agents: Optional[list] = None,
    planned_role_types: Optional[list] = None,
    msg_id: Optional[str] = None,
    step_id: Optional[str] = None,
) -> tuple[str, str]:
    """写 msg-files 工单，返回 (msg_id, path)。"""
    nid = msg_id or generate_msg_id()
    msg_files = os.path.join(data_dir, "msg-files")
    os.makedirs(msg_files, exist_ok=True)
    wo_path = os.path.join(msg_files, f"{nid}.md")
    sid = step_id or f"s{step_num}"
    rf_step = os.path.join(data_dir, "msg-results", task_id, f"step-{sid}.json")
    rf_legacy = os.path.join(data_dir, "msg-results", f"{task_id}.json")
    df = os.path.join(data_dir, "deliverables", task_id)

    n_person = ""
    n_role = ""
    if planned_agents:
        n_person = planned_agents[0]
        n_role = agent_to_role(n_person)
    elif planned_role_types:
        from .locale.role_labels import role_type_to_zh, role_type_candidates
        rt = int(planned_role_types[0])
        n_role = role_type_to_zh(rt, data_dir)
        cands = role_type_candidates(rt, data_dir)
        n_person = cands[0] if cands else ""

    body = f"""# {to_role} — Pipeline Step{step_num}

## 工单元数据
| 字段 | 值 |
|------|-----|
| task_id | {task_id} |
| step_id | {sid} |
| pipeline_step | {step_num} |
| 发起人 | {from_person} ({from_role}) |
| 当前执行人 | {to_person} ({to_role}) |
| 下一步执行人 | {n_person or '(末步)'} ({n_role or '-'}) |
| 状态 | running |
| summary | {summary[:300]} |

## 任务描述
请执行当前角色职责，完成 Step{step_num}。

## 必读规则
- {data_dir}/rules/pipeline-agent-paths.md
- {data_dir}/rules/closed-loop-task-design.md
- {data_dir}/roles/json/role-flow.json

## 交付物
1. `{df}/` 下本步产出
2. **必须**写入 `{rf_step}`（主）
3. 可选 mirror `{rf_legacy}`（兼容旧脚本）

## msg-results 格式（必填）
```json
{{
  "task_id": "{task_id}",
  "step_id": "{sid}",
  "agent": "{to_person}",
  "role_type": <int, see role-types.json>,
  "pipeline_step": {step_num},
  "conclusion": "done",
  "summary": "<本步结论>",
  "timestamp": "<ISO8601>"
}}
```

⚠️ 无 msg-results 文件 = 本步未完成。stdout / replies 不算完成。
"""
    with open(wo_path, "w", encoding="utf-8") as f:
        f.write(body)
    return nid, wo_path


def next_planned_person(chain: list) -> tuple[str, str]:
    """从 chain[0].planned_agents 取下一步。"""
    if not chain:
        return "", ""
    planned = chain[0].get("planned_agents") or []
    if not planned:
        return "", ""
    p = planned[0]
    return agent_to_role(p), p
