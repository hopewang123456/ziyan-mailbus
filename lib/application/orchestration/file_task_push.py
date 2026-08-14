"""Cline/OpenCode 文件任务推送 — 混合模式（方案三）。"""

from __future__ import annotations

import os
from typing import Any, Optional, Tuple

from lib.infra.utils import json_read

FILE_TASK_AGENT_TYPES = frozenset({"cline", "opencode", "codex", "claude_code"})


def agent_uses_file_task_push(agent_type: str, agent_cfg: dict | None = None) -> bool:
    if (agent_type or "").strip() in FILE_TASK_AGENT_TYPES:
        return True
    return bool((agent_cfg or {}).get("file_task_for_executable"))


def should_file_task_push(
    agent_type: str,
    agent_cfg: dict | None,
    entry_dict: dict,
    raw_content: str,
) -> bool:
    """可执行任务是否走 msg-files 工单推送（Codex/Cline 全量；Hermes 超阈值）。"""
    if not is_executable_task(entry_dict):
        return False
    if (agent_type or "").strip() in FILE_TASK_AGENT_TYPES:
        return True
    if (agent_cfg or {}).get("file_task_for_executable"):
        return True
    threshold = int((agent_cfg or {}).get("file_task_content_threshold") or 0)
    if threshold and len(raw_content or "") > threshold:
        return True
    return False


def is_executable_task(msg: Any) -> bool:
    if not isinstance(msg, dict):
        return False
    mtype = (msg.get("type") or "notice").lower()
    action = msg.get("action") or {}
    execute = action.get("execute", mtype == "task") if isinstance(action, dict) else True
    if mtype in ("task", "question") and execute:
        return True
    if mtype == "task_reply":
        return True
    return False


def result_path_for_msg(data_dir: str, msg_id: str) -> str:
    return os.path.join(data_dir, "msg-results", f"{msg_id}.json")


def ensure_file_task_work_order(
    data_dir: str,
    agent_name: str,
    msg_entry: dict,
) -> Tuple[str, str, str]:
    """写 work-orders（pipeline）或 msg-files 工单，返回 (msg_id, work_order_path, result_path)。"""
    msg_id = (msg_entry.get("id") or "").strip()
    if not msg_id:
        from lib.infra.utils import generate_msg_id
        msg_id = generate_msg_id()
        msg_entry["id"] = msg_id

    task_id = (msg_entry.get("task_id") or "").strip()
    step_id = (msg_entry.get("step_id") or "").strip()
    if not step_id and task_id:
        import re
        content = msg_entry.get("content") or ""
        m = re.search(r"step_id=([^\s\n]+)", content)
        if m:
            step_id = m.group(1)

    if task_id and step_id:
        from lib.application.orchestration.pipeline.work_order import write_pipeline_work_order

        step_num = int(msg_entry.get("pipeline_step") or msg_entry.get("step") or 1)
        _, wo_path = write_pipeline_work_order(
            data_dir,
            task_id=task_id,
            step_num=step_num,
            to_person=agent_name,
            to_role=msg_entry.get("to_role") or agent_name,
            from_person=msg_entry.get("from") or "mailbus",
            summary=(msg_entry.get("content") or "")[:300],
            msg_id=msg_id,
            step_id=step_id,
        )
        rf_path = os.path.join(data_dir, "msg-results", task_id, f"step-{step_id}.json")
        return msg_id, wo_path, rf_path

    msg_files = os.path.join(data_dir, "msg-files")
    os.makedirs(msg_files, exist_ok=True)
    wo_path = os.path.join(msg_files, f"{msg_id}.md")
    rf_path = result_path_for_msg(data_dir, msg_id)

    if os.path.isfile(wo_path):
        return msg_id, wo_path, rf_path

    from_ = msg_entry.get("from", "?")
    mtype = msg_entry.get("type", "task")
    content = (msg_entry.get("content") or "").strip()
    task_id = msg_entry.get("task_id") or ""

    body = f"""# 任务 — {agent_name}

| 字段 | 值 |
|------|-----|
| message_id | {msg_id} |
| task_id | {task_id or '-'} |
| from | {from_} |
| type | {mtype} |
| agent | {agent_name} |

## 任务内容
{content}

## 完成要求
1. 读取本文件中的完整指令并执行
2. **必须**将结果写入 `{rf_path}`（JSON）
3. 结果格式示例：
```json
{{
  "template": "task-report",
  "msg_id": "{msg_id}",
  "agent": "{agent_name}",
  "conclusion": "done",
  "summary": "≤200字结论",
  "timestamp": "<ISO8601>"
}}
```

⚠️ 无结果文件 = 未完成。禁止只回「完成回执」而不执行任务。
"""
    with open(wo_path, "w", encoding="utf-8") as f:
        f.write(body)
    return msg_id, wo_path, rf_path


def build_file_task_push_body(
    *,
    from_: str,
    msg_id: str,
    msg_type: str,
    wo_path: str,
    result_path: str,
) -> str:
    return (
        f"📬 {msg_type} | {from_} | id={msg_id}\n"
        f"📄 任务文件: {wo_path}\n"
        f"📄 结果写入: {result_path}\n\n"
        "⚠️ 约束：先读任务文件 → 执行 → 写结果 JSON → 再回复。\n"
        "❌ 禁止只回「完成回执」而不写结果文件。\n"
        "---\n"
    )


def read_msg_result(data_dir: str, msg_id: str) -> Optional[dict]:
    path = result_path_for_msg(data_dir, msg_id)
    if not os.path.isfile(path):
        return None
    data = json_read(path, {})
    return data if isinstance(data, dict) and data else None


def verify_file_task_delivery(
    data_dir: str,
    agent_name: str,
    msg_entry: dict,
    *,
    reply_text: str = "",
) -> Tuple[bool, str]:
    """Cline/OpenCode/Codex 可执行任务：须 msg-results/{msg_id}.json。"""
    from lib.composition import is_phantom_reply_text

    if not is_executable_task(msg_entry):
        return True, "not_executable"
    mid = msg_entry.get("id") or ""
    if not mid:
        return True, "no_msg_id"
    result = read_msg_result(data_dir, mid)
    if result:
        agent = (result.get("agent") or "").strip()
        if agent and agent != agent_name:
            return False, "wrong_agent_result"
        return True, "ok"
    if reply_text and is_phantom_reply_text(reply_text, msg_type=msg_entry.get("type", "")):
        return False, "phantom_reply_text"
    return False, "missing_msg_results"
