"""任务完成判定 — pipeline / 文件任务统一入口。

SoT：msg-results/（及 pipeline step 结果）。replies/*.json 仅作通知，不参与 FSM 完成判定。
"""

from __future__ import annotations

from typing import Optional, Tuple


def is_task_complete(
    data_dir: str,
    agent_name: str,
    msg_entry: dict,
    *,
    agent_type: str = "",
    reply_text: str = "",
) -> Tuple[bool, str]:
    """返回 (complete, reason)。complete=True 表示任务可视为已交付。"""
    from .file_task_push import (
        agent_uses_file_task_push,
        should_file_task_push,
        verify_file_task_delivery,
    )
    from .pipeline_task import extract_task_id, is_pipeline_execute_message, verify_pipeline_step_delivery

    if not isinstance(msg_entry, dict):
        return False, "invalid_entry"

    agent_cfg = {}
    if data_dir:
        from .utils import json_read as _jr

        agent_cfg = (_jr(f"{data_dir}/config.json", {}).get("agents") or {}).get(agent_name) or {}

    content = msg_entry.get("content", "")
    mtype = msg_entry.get("type", "notice")

    if should_file_task_push(agent_type, agent_cfg, msg_entry, content):
        ok, reason = verify_file_task_delivery(
            data_dir, agent_name, msg_entry, reply_text=reply_text,
        )
        return ok, reason

    if is_pipeline_execute_message(msg_entry, data_dir):
        ok, reason = verify_pipeline_step_delivery(data_dir, agent_name, msg_entry)
        return ok, reason

    tid = extract_task_id(content or "")
    if tid or agent_uses_file_task_push(agent_type, agent_cfg):
        ok, reason = verify_pipeline_step_delivery(data_dir, agent_name, msg_entry)
        if ok:
            return True, reason
        if reason == "not_pipeline":
            ok, reason = verify_file_task_delivery(
                data_dir, agent_name, msg_entry, reply_text=reply_text,
            )
            return ok, reason
        return False, reason

    # 非 pipeline / 非文件任务：notice 等由 ack 驱动，replies 不算完成
    if mtype in ("notice", "broadcast", "system"):
        return False, "notice_not_task_complete"
    return False, "not_applicable"
