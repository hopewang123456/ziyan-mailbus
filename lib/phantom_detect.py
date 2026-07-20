"""Phantom completion 检测 — agent 回执无实质产出。"""

from __future__ import annotations

from typing import Tuple

PHANTOM_REPLY_MARKERS = (
    "✅ 任务完成回执",
    "任务完成回执",
    "已完成，无额外输出",
    "AI SDK Warning",
)

PHANTOM_MIN_SUBSTANCE_LEN = 24


def is_phantom_reply_text(text: str, *, msg_type: str = "") -> bool:
    """回复文本是否为典型空回执（无实质 stdout / 结果）。"""
    if (msg_type or "").strip().lower() in ("notice", "broadcast", "system"):
        return False
    body = (text or "").strip()
    if not body:
        return True
    if any(m in body for m in PHANTOM_REPLY_MARKERS):
        if len(body) < 120:
            return True
    if body.startswith("AI SDK Warning") and len(body) < 200:
        return True
    return len(body) < PHANTOM_MIN_SUBSTANCE_LEN


def check_phantom_completion(
    data_dir: str,
    agent_name: str,
    msg_entry: dict,
    *,
    reply_text: str = "",
    agent_type: str = "",
) -> Tuple[bool, str]:
    """返回 (is_phantom, reason)。pipeline / 文件任务无 msg-results 或空回执视为 phantom。"""
    from .task_completion import is_task_complete

    if not isinstance(msg_entry, dict):
        return False, ""

    complete, reason = is_task_complete(
        data_dir, agent_name, msg_entry, agent_type=agent_type, reply_text=reply_text,
    )
    if complete:
        return False, ""
    if reason in ("missing_msg_results", "phantom_reply_text", "inconclusive"):
        return True, reason
    if reason == "notice_not_task_complete":
        return False, ""
    return False, reason
