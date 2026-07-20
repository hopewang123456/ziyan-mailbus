"""verify 失败升级通知。"""
from __future__ import annotations

from typing import Any, Dict, Optional


def notify_verify_failure(
    data_dir: str,
    *,
    task_id: str,
    agent: str,
    role_label: str,
    reason: str,
    attempt: int,
    escalate_cfg: Optional[Dict[str, Any]] = None,
) -> None:
    """按 attempt 向 escalate_cfg 指定 agent 写 inbox 提醒（best-effort）。"""
    if not data_dir or not task_id:
        return
    target = (escalate_cfg or {}).get(str(attempt))
    if not target:
        return
    try:
        from ..models import Inbox
        from ..utils import json_read, json_write, _now_iso, resolve_paths

        paths = resolve_paths(data_dir)
        inbox_path = f"{paths['inbox']}/{target}/inbox.json"
        inbox = Inbox.from_dict(json_read(inbox_path, {})) if inbox_path else None
        if inbox is None:
            inbox = Inbox(agent=target)
        inbox.messages.append({
            "id": f"verify-fail-{task_id}-{attempt}",
            "from": "mailbus",
            "to": target,
            "type": "notice",
            "priority": "high",
            "state": "pending",
            "task_id": task_id,
            "content": (
                f"⚠️ verify 失败 task={task_id} agent={agent} role={role_label} "
                f"attempt={attempt}: {reason}"
            ),
            "created_at": _now_iso(),
        })
        inbox.has_unread = True
        json_write(inbox_path, inbox.to_dict())
    except Exception:
        pass
