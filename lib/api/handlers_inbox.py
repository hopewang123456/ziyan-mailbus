"""
ziyan-mailbus HTTP API — Inbox 相关路由处理器

处理: /api/inbox/, /api/mark-read/, /api/send-msg, /api/replies, /api/actions/update/
"""

import os
import json
from lib.models import Inbox, Message, MsgStatus, Priority, MsgType
from lib.utils import json_read, json_write, resolve_paths, _now_iso, build_message
from lib.scanner import build_queues, update_message_status
from lib.pusher import push_messages, resolve_cli_chain


def handle_inbox(handler, agent: str):
    """GET /api/inbox/<agent> — 获取指定 agent 的 inbox 内容
    
    支持查询参数:
        ?status_filter=pending  — 只返回待处理消息（默认返回全部）
    """
    from urllib.parse import urlparse, parse_qs
    qs = parse_qs(urlparse(handler.path).query)
    status_filter = qs.get("status_filter", [None])[0]
    
    paths = resolve_paths(handler.data_dir)
    inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
    if not os.path.exists(inbox_file):
        handler._send_json({"agent": agent, "messages": [], "has_unread": False}, 200)
        return
    data = json_read(inbox_file, {})
    if not data:
        handler._send_json({"agent": agent, "messages": [], "has_unread": False}, 200)
        return
    inbox = Inbox.from_dict(data)
    msg_count = len(inbox.messages)
    # P4: 非 terminal 态（pending/pushed/acknowledged/processing）视为未处理
    terminal_states = {"done", "closed", "rejected", "failed", "archived", "sent"}
    unread = sum(1 for m in inbox.messages
                 if (inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", ""))
                 not in terminal_states)
    msgs_out = []
    for m in inbox.messages:
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
    })


def handle_mark_read(handler, agent: str):
    """POST /api/mark-read/<agent> — 标记 agent 的指定消息为已读"""
    body = handler._read_post_body()
    msg_ids = body.get("msg_ids", [])
    if not msg_ids:
        handler._send_json({"error": "缺少 msg_ids"}, 400)
        return
    paths = resolve_paths(handler.data_dir)
    inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
    data = json_read(inbox_file, {})
    if not data:
        handler._send_json({"error": "inbox not found"}, 404)
        return
    inbox = Inbox.from_dict(data)
    ts = __import__("datetime").datetime.now().isoformat()
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
        handler._send_json({"error": "缺少 to 或 content"}, 400)
        return
    from_ = body.get("from", "api")
    priority = body.get("priority", "normal")
    msg_type = body.get("type", "notice")
    if to not in handler.agents:
        handler._send_json({"error": f"agent '{to}' 未注册"}, 404)
        return
    msg = build_message(from_, to, content, msg_type, priority)
    paths = resolve_paths(handler.data_dir)
    inbox_file = f"{paths['inbox']}/{to}/inbox.json"
    inbox_data = json_read(inbox_file, {"agent": to, "has_unread": False, "messages": [], "since": _now_iso()})
    inbox = Inbox.from_dict(inbox_data)
    inbox.has_unread = True
    inbox.messages.append(msg.to_dict())
    json_write(inbox_file, inbox.to_dict())

    # 即时推送：写完后立即扫描并推送，不等下次 cron
    try:
        # 获取 agent 配置和 CLI 命令
        agent_cfg = handler.agents.get(to, {})
        model_alias = (agent_cfg.get("models") or [""])[0]
        cli_chain = resolve_cli_chain(agent_cfg, model_alias, handler.agent_types)
        if cli_chain:
            cli_cmds = [c[0] for c in cli_chain]
            push_messages(handler.data_dir, to, [msg.to_dict()],
                          cli_cmd=cli_cmds, auto_ack=True)
    except Exception:
        pass  # 推送失败不影响消息已写入

    handler._send_json({"status": "ok", "msg_id": msg.id})


def handle_replies(handler):
    """GET /api/replies — 获取所有 agent 的回复数据"""
    paths = resolve_paths(handler.data_dir)
    reply_base = os.path.join(paths["inbox"])
    results = {}
    for name in handler.agents:
        inbox_file = f"{reply_base}/{name}/inbox.json"
        data = json_read(inbox_file, {})
        if not data or "agent" not in data:
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
        handler._send_json({"error": "缺少 action"}, 400)
        return
    paths = resolve_paths(handler.data_dir)
    inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
    data = json_read(inbox_file, {})
    if not data:
        handler._send_json({"error": "inbox not found"}, 404)
        return
    inbox = Inbox.from_dict(data)
    for i, m in enumerate(inbox.messages):
        mid = inbox.msg_field(m, "id", "")
        if mid == msg_id:
            inbox.messages[i]["action"] = action
            json_write(inbox_file, inbox.to_dict())
            handler._send_json({"status": "ok"})
            return
    handler._send_json({"error": "msg not found"}, 404)
