"""Pipeline 步骤工单 — SoT: store/work-orders/{task_id}/step-{step_id}.md

过渡期双轨：同时写 msg-files/{msg_id}.md 供旧 push 路径解析。
"""

from __future__ import annotations

import os
import re
from typing import Optional, Tuple

from lib.infra.constants import MAILBUS_ROOT
from lib.application.orchestration.pipeline.chain import agent_to_role
from lib.infra.utils import generate_msg_id

_STATUS_RE = re.compile(r"<!--\s*status:\s*([^\s|>-]+)", re.I)


def work_order_path(data_dir: str, task_id: str, step_id: str) -> str:
    return os.path.join(data_dir, "work-orders", task_id, f"step-{step_id}.md")


def legacy_msg_file_path(data_dir: str, msg_id: str) -> str:
    return os.path.join(data_dir, "msg-files", f"{msg_id}.md")


def resolve_work_order_path(
    data_dir: str,
    *,
    task_id: str = "",
    step_id: str = "",
    msg_id: str = "",
) -> Optional[str]:
    """优先 work-orders，回退 msg-files（#3 双轨过渡）。"""
    if task_id and step_id:
        wo = work_order_path(data_dir, task_id, step_id)
        if os.path.isfile(wo):
            return wo
    if msg_id:
        legacy = legacy_msg_file_path(data_dir, msg_id)
        if os.path.isfile(legacy):
            return legacy
    if task_id and step_id:
        wo = work_order_path(data_dir, task_id, step_id)
        return wo if os.path.isfile(wo) else None
    return None


def _load_template() -> str:
    tpl_path = MAILBUS_ROOT / "rules" / "common" / "work-order-template.md"
    if tpl_path.is_file():
        return tpl_path.read_text(encoding="utf-8")
    return "# Work Order step-{step_id}\n\n<!-- status: pending -->\n\n## 目标\n\n## 约束\n\n## 验收\n"


def parse_work_order_status(content: str) -> str:
    m = _STATUS_RE.search(content or "")
    return m.group(1).lower() if m else "pending"


def validate_work_order_schema(content: str) -> Tuple[bool, list[str]]:
    """校验工单必含字段（Intent/Scope/Acceptance/result_path 或等价段落）。"""
    errors: list[str] = []
    if not content or len(content.strip()) < 20:
        errors.append("empty_content")
        return False, errors
    required_markers = (
        "task_id",
        "step_id",
        "msg-results",
    )
    for marker in required_markers:
        if marker not in content:
            errors.append(f"missing:{marker}")
    return len(errors) == 0, errors


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
    on_failure: str = "写 msg-results conclusion=failed + reason；Dashboard 可 recover --continue",
    role_type: Optional[int] = None,
) -> tuple[str, str]:
    """写 work-orders 工单（+ msg-files 镜像），返回 (msg_id, primary_path)。"""
    nid = msg_id or generate_msg_id()
    sid = step_id or f"s{step_num}"
    rf_step = os.path.join(data_dir, "msg-results", task_id, f"step-{sid}.json")
    df = os.path.join(data_dir, "deliverables", task_id)

    n_person = ""
    n_role = ""
    if planned_agents:
        n_person = planned_agents[0]
        n_role = agent_to_role(n_person)
    elif planned_role_types:
        from lib.composition import get_locale

        locale = get_locale(data_dir)
        rt = int(planned_role_types[0])
        n_role = locale.role_type_to_zh(rt)
        cands = locale.role_type_candidates(rt)
        n_person = cands[0] if cands else ""

    tpl = _load_template()
    intent = summary[:300] if summary else f"完成 Pipeline Step{step_num}（{to_role}）"
    scope = f"当前执行人 {to_person}；必读 store/rules 与 role-flow.json"
    acceptance = f"写入 `{rf_step}`；deliverables 见 `{df}/`"
    decomposition_block = ""
    if role_type is not None:
        decomposition_block = f"\n## Role Type\n{role_type}\n"

    tpl = re.sub(
        r"<!--\s*status:.*?-->",
        "<!-- status: in_progress -->",
        tpl,
        count=1,
        flags=re.I | re.S,
    )
    tpl = tpl.replace("step-{step_id}", f"step-{sid}")

    body = f"""{tpl}

---

## 工单元数据
| 字段 | 值 |
|------|-----|
| task_id | {task_id} |
| step_id | {sid} |
| pipeline_step | {step_num} |
| message_id | {nid} |
| 发起人 | {from_person} ({from_role}) |
| 当前执行人 | {to_person} ({to_role}) |
| 下一步执行人 | {n_person or '(末步)'} ({n_role or '-'}) |
| 状态 | in_progress |
| result_path | {rf_step} |

## Intent
{intent}

## Scope
{scope}

## Acceptance
{acceptance}

## 本轮 Context
- 上一步 msg-results 摘要见 pipeline trigger 注入
- 工单路径：`store/work-orders/{task_id}/step-{sid}.md`

## On Failure
{on_failure}
{decomposition_block}
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

⚠️ 无 msg-results 文件 = 本步未完成。stdout / replies / patch 须经 Delivery Normalizer 归一化后 FSM 才推进。
"""
    wo_dir = os.path.join(data_dir, "work-orders", task_id)
    os.makedirs(wo_dir, exist_ok=True)
    wo_path = work_order_path(data_dir, task_id, sid)
    with open(wo_path, "w", encoding="utf-8") as f:
        f.write(body)

    msg_files = os.path.join(data_dir, "msg-files")
    os.makedirs(msg_files, exist_ok=True)
    legacy_path = legacy_msg_file_path(data_dir, nid)
    with open(legacy_path, "w", encoding="utf-8") as f:
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
