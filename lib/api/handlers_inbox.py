"""
ziyan-mailbus HTTP API — Inbox 相关路由处理器

处理: /api/inbox/, /api/mark-read/, /api/send-msg, /api/replies, /api/actions/update/
"""

import os
import json
from lib.domain.models import Inbox, Message, MsgStatus, Priority, MsgType
from lib.infra.utils import json_read, json_write, resolve_paths, _now_iso, build_message
from lib.application.scan import build_queues, update_message_status
from lib.application.push.pusher import push_messages, resolve_cli_chain
from lib.infra.clock import now_dt, now_iso, now_ts, now_utc_dt


def handle_inbox(handler, agent: str):
    """GET /api/inbox/<agent> — 获取指定 agent 的 inbox 内容
    
    支持查询参数:
        ?status_filter=pending  — 只返回待处理消息（默认返回全部）
        ?limit=100              — 只返回最近 N 条（按 created_at 倒序，减轻 Dashboard 负载）
    """
    from lib.api.security import validate_agent_name
    if not validate_agent_name(agent, handler.agents):
        handler._send_api_error("not_found", 404, detail=f"未知 agent: {agent}")
        return
    from urllib.parse import urlparse, parse_qs
    qs = parse_qs(urlparse(handler.path).query)
    status_filter = qs.get("status_filter", [None])[0]
    try:
        msg_limit = int(qs.get("limit", ["0"])[0])
    except (ValueError, TypeError):
        msg_limit = 0
    
    paths = resolve_paths(handler.data_dir)
    inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
    if not os.path.exists(inbox_file):
        handler._send_json({"agent": agent, "messages": [], "has_unread": False}, 200)
        return
    data = json_read(inbox_file, {})
    if not data:
        handler._send_json({"agent": agent, "messages": [], "has_unread": False}, 200)
        return
    # v4.0: 兼容 inbox.json dict→list 格式迁移
    if isinstance(data, list):
        data = {"agent": agent, "has_unread": True, "messages": data, "since": _now_iso()}
    inbox = Inbox.from_dict(data)
    msg_count = len(inbox.messages)
    # P4: 非 terminal 态（pending/pushed/acknowledged/processing）视为未处理
    terminal_states = {"done", "closed", "rejected", "failed", "archived", "sent"}
    unread = sum(1 for m in inbox.messages
                 if (inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", ""))
                 not in terminal_states)
    msgs_out = []
    # limit>0：按时间倒序取最近 N 条（Dashboard 用，避免一次序列化整个 inbox）
    source_msgs = list(inbox.messages)
    if msg_limit > 0 and not status_filter:
        def _ts(m):
            return inbox.msg_field(m, "created_at", "") or inbox.msg_field(m, "received_at", "") or ""
        source_msgs = sorted(source_msgs, key=_ts, reverse=True)[:msg_limit]
    for m in source_msgs:
        msg = Message.from_dict(m) if isinstance(m, dict) else m
        # P4: 支持 status_filter 过滤
        if status_filter:
            cur_state = msg.state or msg.status
            if cur_state != status_filter:
                continue
        msgs_out.append({
            "id": msg.id, "from": msg.from_, "type": msg.type,
            "priority": msg.priority, "content": msg.content,
            "status": msg.status, "state": msg.state or msg.status, "attachments": msg.attachments or [],
            "created_at": msg.created_at, "pushed_count": msg.pushed_count,
        })
    handler._send_json({
        "agent": agent, "has_unread": inbox.has_unread,
        "total": msg_count, "unread": unread, "messages": msgs_out,
        "truncated": bool(msg_limit > 0 and msg_count > len(msgs_out)),
    })


def handle_mark_read(handler, agent: str):
    """POST /api/mark-read/<agent> — 标记 agent 的指定消息为已读"""
    body = handler._read_post_body()
    msg_ids = body.get("msg_ids", [])
    if not msg_ids:
        handler._send_api_error("fatal", 400, detail="缺少 msg_ids")
        return
    paths = resolve_paths(handler.data_dir)
    inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
    data = json_read(inbox_file, {})
    if not data:
        handler._send_api_error("not_found", 404, detail="inbox not found")
        return
    # v4.0: 兼容 inbox.json dict→list 格式迁移
    if isinstance(data, list):
        data = {"agent": agent, "has_unread": True, "messages": data, "since": _now_iso()}
    inbox = Inbox.from_dict(data)
    ts = __import__("datetime").now_dt().isoformat()
    for mid in msg_ids:
        inbox.set_msg_status(mid, MsgStatus.ACKNOWLEDGED, acknowledged_at=ts)
        inbox.set_msg_status(mid, MsgStatus.ACKNOWLEDGED, state=MsgStatus.DONE, done_at=ts)
    # P4: 非 terminal 态才视为有未处理消息
    terminal_states = {"done", "closed", "rejected", "failed", "archived", "sent"}
    inbox.has_unread = any((inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", "")) not in terminal_states for m in inbox.messages)
    json_write(inbox_file, inbox.to_dict())
    handler._send_json({"status": "ok", "marked": len(msg_ids)})


def handle_send_msg(handler):
    """GET/POST /api/send-msg — 手动发送消息"""
    if handler.command == "POST":
        body = handler._read_post_body()
    else:
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(handler.path).query)
        body = {k: v[0] if v else "" for k, v in qs.items()}

    to = body.get("to", "")
    content = body.get("content", "")
    if not to or not content:
        handler._send_api_error("fatal", 400, detail="缺少 to 或 content")
        return
    from_ = body.get("from", "api")
    priority = body.get("priority", "normal")
    msg_type = body.get("type", "notice")
    if to not in handler.agents:
        handler._send_api_error("not_found", 404, detail=f"agent '{to}' 未注册")
        return
    msg_dict = build_message(from_, to, content, msg_type, priority).to_dict()
    task_id = body.get("task_id", "").strip()
    if task_id:
        msg_dict["task_id"] = task_id
    paths = resolve_paths(handler.data_dir)
    inbox_file = f"{paths['inbox']}/{to}/inbox.json"
    inbox_data = json_read(inbox_file, {"agent": to, "has_unread": False, "messages": [], "since": _now_iso()})
    # v4.0: 兼容 inbox.json dict→list 格式迁移
    if isinstance(inbox_data, list):
        inbox_data = {"agent": to, "has_unread": True, "messages": inbox_data, "since": _now_iso()}
    inbox = Inbox.from_dict(inbox_data)
    inbox.has_unread = True
    inbox.messages.append(msg_dict)
    json_write(inbox_file, inbox.to_dict())

    # 即时推送：写完后立即扫描并推送，不等下次 cron
    try:
        from ..model_router import is_no_llm_notice
        from lib.application.scan import finalize_auto_ack

        if is_no_llm_notice(msg_dict):
            finalize_auto_ack(handler.data_dir, to, msg_dict["id"], msg_dict)
        else:
            agent_cfg = handler.agents.get(to, {})
            cli_chain = resolve_cli_chain(agent_cfg, handler.agent_types)
            if cli_chain:
                cli_cmds = [c[0] for c in cli_chain]
                from lib.application.orchestration.pipeline.task import should_auto_ack_message
                auto_ack = should_auto_ack_message(
                    msg_dict, handler.data_dir, agent_cfg.get("type", ""),
                )
                push_messages(handler.data_dir, to, [msg_dict],
                              cli_cmd=cli_cmds, auto_ack=auto_ack)
    except Exception:
        pass  # 推送失败不影响消息已写入

    handler._send_json({"status": "ok", "msg_id": msg_dict["id"]})


def handle_replies(handler):
    """GET /api/replies — 获取所有 agent 的回复数据"""
    paths = resolve_paths(handler.data_dir)
    reply_base = os.path.join(paths["inbox"])
    results = {}
    for name in handler.agents:
        inbox_file = f"{reply_base}/{name}/inbox.json"
        data = json_read(inbox_file, {})
        if not data:
            continue
        # v4.0: 兼容 inbox.json dict→list 格式迁移
        if isinstance(data, list):
            data = {"agent": name, "has_unread": True, "messages": data, "since": _now_iso()}
        if "agent" not in data:
            continue
        try:
            inbox = Inbox.from_dict(data)
        except (KeyError, TypeError):
            continue
        replies = []
        for m in inbox.messages:
            mtype = inbox.msg_field(m, "type", "")
            if mtype in ("reply", "forward", "task_reply"):
                msg = Message.from_dict(m) if isinstance(m, dict) else m
                replies.append({
                    "id": msg.id, "from": msg.from_, "type": msg.type,
                    "content": msg.content, "status": msg.status, "state": msg.state or msg.status,
                    "created_at": msg.created_at,
                })
        if replies:
            results[name] = replies
    handler._send_json(results)


def handle_actions_update(handler, agent: str, msg_id: str):
    """POST /api/actions/update/<agent>/<msg_id> — 更新消息的 action 字段"""
    body = handler._read_post_body()
    action = body.get("action", {})
    if not action:
        handler._send_api_error("fatal", 400, detail="缺少 action")
        return
    paths = resolve_paths(handler.data_dir)
    inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
    data = json_read(inbox_file, {})
    if not data:
        handler._send_api_error("not_found", 404, detail="inbox not found")
        return
    # v4.0: 兼容 inbox.json dict→list 格式迁移
    if isinstance(data, list):
        data = {"agent": agent, "has_unread": True, "messages": data, "since": _now_iso()}
    inbox = Inbox.from_dict(data)
    for i, m in enumerate(inbox.messages):
        mid = inbox.msg_field(m, "id", "")
        if mid == msg_id:
            inbox.messages[i]["action"] = action
            json_write(inbox_file, inbox.to_dict())
            handler._send_json({"status": "ok"})
            return
    handler._send_api_error("not_found", 404, detail="msg not found")
