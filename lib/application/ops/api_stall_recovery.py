"""API 断连停滞：冷却重推 + Mailbus 面板告警。"""

from __future__ import annotations

from lib.infra.clock import now_dt, now_ts, now_utc_dt
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from lib.composition import get_ops
from lib.infra.mbus_log import info, warn
from lib.domain.models import Inbox, MsgStatus
from lib.application.orchestration.pipeline.task import extract_task_id
from lib.infra.utils import json_read, json_write, resolve_paths, _now_iso


def _parse_iso(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def repush_after_elapsed(msg: dict) -> bool:
    """repush_after 为空或已到期 → 可重推。"""
    raw = (msg.get("repush_after") if isinstance(msg, dict) else "") or ""
    if not raw:
        return True
    target = _parse_iso(raw)
    if not target:
        return True
    return now_utc_dt() >= target.astimezone(timezone.utc)


def repush_after_remaining_minutes(msg: dict) -> float:
    raw = (msg.get("repush_after") if isinstance(msg, dict) else "") or ""
    target = _parse_iso(raw)
    if not target:
        return 0.0
    delta = (target.astimezone(timezone.utc) - now_utc_dt()).total_seconds() / 60.0
    return max(0.0, delta)


def schedule_api_stall_recovery(
    data_dir: str,
    agent_name: str,
    msg_id: str,
    *,
    reason: str,
    task_id: str = "",
    reply_excerpt: str = "",
) -> bool:
    """
    标记 API 停滞、设置 repush_after 冷却，并向舰队监控 /api/alerts 告警（Mailbus 面板）。
  返回是否新调度（非重复告警）。
    """
    if not agent_name or not msg_id:
        return False
    config = json_read(os.path.join(data_dir, "config.json"), {})
    ops = get_ops()
    wait_min = ops.api_stall_repush_wait_minutes(config, data_dir)
    now = now_utc_dt()
    repush_after = (now + timedelta(minutes=wait_min)).isoformat()

    paths = resolve_paths(data_dir)
    inbox_file = os.path.join(paths["inbox"], agent_name, "inbox.json")
    inbox_data = json_read(inbox_file, {})
    if not inbox_data:
        return False
    inbox = Inbox.from_dict(inbox_data)
    changed = False
    for m_raw in inbox.messages:
        mid = inbox.msg_field(m_raw, "id", "")
        if mid != msg_id:
            continue
        if not repush_after_elapsed(m_raw if isinstance(m_raw, dict) else {}):
            return False
        count = int(inbox.msg_field(m_raw, "api_stall_count", 0) or 0) + 1
        inbox.set_msg_status(
            mid,
            MsgStatus.PROCESSING,
            state=MsgStatus.PROCESSING,
            api_stall_at=_now_iso(),
            api_stall_reason=reason,
            api_stall_count=count,
            repush_after=repush_after,
            done_note=f"api_stall:{reason}",
        )
        changed = True
        break
    if not changed:
        return False
    json_write(inbox_file, inbox.to_dict())

    tid = task_id or ""
    excerpt = (reply_excerpt or "")[:160].replace("\n", " ")
    panel_hint = "舰队监控 → 告警"
    message = (
        f"{agent_name} 任务因 API/网络不可达已停止（{reason}）。"
        f"约 {wait_min:.0f} 分钟后自动重推。"
        f" msg={msg_id}"
        + (f" task={tid}" if tid else "")
        + (f" | {excerpt}" if excerpt else "")
        + f" | {panel_hint}"
    )
    ops.push_alert(
        data_dir,
        "api_unreachable",
        "warn",
        agent=agent_name,
        message=message,
        dedupe_key=f"api_unreachable:{agent_name}:{msg_id}",
    )
    info(f"[api_stall] scheduled {agent_name} msg={msg_id[:24]} repush_after={repush_after}")
    return True


def maybe_release_api_stall_for_repush(
    data_dir: str,
    agent_name: str,
    m_raw: dict,
    inbox: Inbox,
    *,
    agents: dict,
) -> bool:
    """
    processing 且 CLI 已退出：若检测到 API 停滞且冷却结束 → 重置 pending 以便 scan 重推。
    若刚检测到停滞 → 调度冷却 + 告警。
    返回是否修改了 inbox。
    """
    from .self_heal import agent_cli_active_for

    mid = inbox.msg_field(m_raw, "id", "")
    content = inbox.msg_field(m_raw, "content", "") or ""
    tid = extract_task_id(content) or inbox.msg_field(m_raw, "task_id", "") or ""
    paths = resolve_paths(data_dir)
    inbox_file = os.path.join(paths["inbox"], agent_name, "inbox.json")

    if agent_cli_active_for(agent_name, agents, msg_id=mid, task_id=tid):
        return False

    reply = get_ops().read_reply_text_for_agent(data_dir, agent_name, mid)
    reason = get_ops().detect_api_stall(reply)
    existing_reason = inbox.msg_field(m_raw, "api_stall_reason", "") or ""
    if not reason and not existing_reason:
        return False

    if not repush_after_elapsed(m_raw if isinstance(m_raw, dict) else {}):
        return False

    stall_reason = reason or existing_reason or "api_network:unknown"
    if not existing_reason:
        schedule_api_stall_recovery(
            data_dir, agent_name, mid,
            reason=stall_reason, task_id=tid, reply_excerpt=reply,
        )
        return True

    inbox.set_msg_status(
        mid,
        MsgStatus.PENDING,
        state=MsgStatus.PENDING,
        acknowledged_at=None,
        received_at=None,
        pushed_count=0,
        last_pushed_at=None,
        done_note=f"api_stall_repush:{stall_reason}",
        repush_after=None,
    )
    json_write(inbox_file, inbox.to_dict())
    warn(f"[api_stall] repush pending {agent_name} msg={mid[:24]} ({stall_reason})")
    return True
