"""验证失败升级 — 抄送调度/方案。"""

from __future__ import annotations

from typing import Optional

from ..jobs import _append_inbox_notice


def notify_verify_failure(
    data_dir: str,
    *,
    task_id: str,
    agent: str,
    role_label: str,
    reason: str,
    attempt: int,
    escalate_cfg: dict,
) -> None:
    msg = (
        f"⚠️ 验证失败 #{attempt}\n"
        f"task: {task_id}\n"
        f"agent: {agent} ({role_label})\n"
        f"reason: {reason}"
    )
    if attempt >= 3:
        to = escalate_cfg.get("3") or "lingzhao"
        _append_inbox_notice(data_dir, to, msg, msg_id=f"verify-esc-{task_id}-{attempt}", no_llm=True)
    elif attempt >= 2:
        to = escalate_cfg.get("2") or "xiaoqi"
        _append_inbox_notice(data_dir, to, msg, msg_id=f"verify-esc-{task_id}-{attempt}", no_llm=True)
