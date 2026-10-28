"""
mailbus HTTP API — Inbox 相关路由处理器

处理: /api/inbox/, /api/mark-read/, /api/send-msg, /api/replies, /api/actions/update/
      /api/inbox/ack/{id}, /api/inbox/{agent}/archive, /api/inbox/{agent}/send
      （后三个为 java 对等面，2026-10-27 PY4-A 补齐）
"""

import os
import json
from lib.domain.models import Inbox, Message, MsgStatus, Priority, MsgType
from lib.infra.utils import json_read, json_write, resolve_paths, _now_iso, build_message
from lib.application.scan import build_queues, update_message_status
from lib.application.push.pusher import push_messages, resolve_cli_chain
from lib.infra.clock import now_dt, now_iso, now_ts, now_utc_dt

# 非终态消息视为未处理（P4 语义，handle_inbox 与 unread 端点共用）
_TERMINAL_STATES = {"done", "closed", "rejected", "failed", "archived", "sent"}


def _read_inbox_file(handler, agent: str):
    """读 agent 的 inbox.json → Inbox 对象（不存在/空则返回空 inbox）。

    兼容历史损坏：inbox.json 被写成纯 messages 数组（v4.0 迁移前格式）。
    """
    paths = resolve_paths(handler.data_dir)
    inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
    if not os.path.exists(inbox_file):
        return None, inbox_file
    data = json_read(inbox_file, {})
    if not data:
        return None, inbox_file
    if isinstance(data, list):
        data = {"agent": agent, "has_unread": True, "messages": data, "since": _now_iso()}
    return Inbox.from_dict(data), inbox_file


def _count_unread(inbox: Inbox) -> int:
    """未读计数：非终态消息数。"""
    return sum(
        1 for m in inbox.messages
        if (inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", ""))
        not in _TERMINAL_STATES
    )


def validate_agent_name_or_404(handler, agent: str) -> bool:
    """校验 agent 名合法性；不合法则写 404 并返回 False（调用方直接 return）。"""
    from lib.api.security import validate_agent_name
    if not validate_agent_name(agent, handler.agents):
        handler._send_api_error("not_found", 404, detail=f"未知 agent: {agent}")
        return False
    return True


def handle_inbox(handler, agent: str):
    """GET /api/inbox/<agent> — 获取指定 agent 的 inbox 内容
    
    支持查询参数:
        ?status_filter=pending  — 只返回待处理消息（默认返回全部）
        ?limit=100              — 只返回最近 N 条（按 created_at 倒序，减轻 Dashboard 负载）
    """
    from lib.api.handlers_system import _reload_store_config
    _reload_store_config(handler)  # 含 D2/D15 内置身份合并
    if not validate_agent_name_or_404(handler, agent):
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
    unread = _count_unread(inbox)
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
    from lib.api.handlers_system import _reload_store_config
    _reload_store_config(handler)  # 含 D2/D15 内置身份合并（send_msg 可直达子言）
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
        from lib.composition import is_no_llm_notice
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


def handle_inbox_ack(handler, msg_id: str):
    """POST /api/inbox/ack/<message_id> — 确认（ack）单条消息（java 对等面）。

    状态跃迁：PENDING → PROCESSING → DONE（与 java InboxService.acknowledge
    同语义；python 侧无 processing 中间态落盘，ack 后直接终态 DONE）。
    """
    from lib.api.handlers_system import _reload_store_config
    _reload_store_config(handler)

    # 消息按 id 落在所属 agent 的 inbox 里——需跨 agent 定位
    paths = resolve_paths(handler.data_dir)
    inbox_root = paths["inbox"]
    if not os.path.isdir(inbox_root):
        handler._send_api_error("not_found", 404, detail=f"not found: {msg_id}")
        return
    for agent in sorted(os.listdir(inbox_root)):
        agent_dir = os.path.join(inbox_root, agent)
        if not os.path.isfile(os.path.join(agent_dir, "inbox.json")):
            continue
        data = json_read(os.path.join(agent_dir, "inbox.json"), {})
        if not data:
            continue
        if isinstance(data, list):
            data = {"agent": agent, "has_unread": True, "messages": data, "since": _now_iso()}
        inbox = Inbox.from_dict(data)
        for m in inbox.messages:
            if inbox.msg_field(m, "id", "") != msg_id:
                continue
            ts = _now_iso()
            inbox.set_msg_status(msg_id, MsgStatus.ACKNOWLEDGED, acknowledged_at=ts)
            inbox.set_msg_status(msg_id, MsgStatus.ACKNOWLEDGED, state=MsgStatus.DONE, done_at=ts)
            inbox.has_unread = any(
                (inbox.msg_field(x, "state", "") or inbox.msg_field(x, "status", ""))
                not in _TERMINAL_STATES
                for x in inbox.messages
            )
            json_write(os.path.join(agent_dir, "inbox.json"), inbox.to_dict())
            handler._send_json({"status": "ok", "id": msg_id, "state": str(MsgStatus.DONE)})
            return
    handler._send_api_error("not_found", 404, detail=f"not found: {msg_id}")


def handle_inbox_archive(handler, agent: str):
    """POST /api/inbox/<agent>/archive — 归档已结算消息（java 对等面）。

    复用 store_cleanup.archive_inbox_backlog（同一份归档判定逻辑）。
    """
    from lib.composition import archive_inbox_backlog
    from lib.api.handlers_system import _reload_store_config
    _reload_store_config(handler)
    if not validate_agent_name_or_404(handler, agent):
        return
    body = handler._read_post_body() or {}
    dry_run = bool(body.get("dry_run"))
    outcome = archive_inbox_backlog(
        handler.data_dir, agent, dry_run=dry_run,
    )
    handler._send_json({
        "status": "ok",
        "agent": agent,
        "archived": outcome.get("archived", 0),
        "ids": outcome.get("ids", []),
    })


def handle_inbox_send(handler, agent: str):
    """POST /api/inbox/<agent>/send — 向指定 agent 发消息（java 对等面）。

    body: {"from": "...", "content": "..."}（java 形状；python 旧端点
    /api/send-msg 用 {"to","content"}，此端点把 to 固定在路径参数上）。
    """
    from lib.api.handlers_system import _reload_store_config
    _reload_store_config(handler)
    if not validate_agent_name_or_404(handler, agent):
        return
    body = handler._read_post_body() or {}
    content = str(body.get("content") or "")
    if not content:
        handler._send_api_error("fatal", 400, detail="缺少 content")
        return
    from_ = str(body.get("from") or "system")
    if from_ not in handler.agents:
        handler._send_api_error("not_found", 404, detail=f"agent '{from_}' 未注册")
        return
    msg_dict = build_message(from_, agent, content, "notice", "normal").to_dict()
    paths = resolve_paths(handler.data_dir)
    inbox_file = f"{paths['inbox']}/{agent}/inbox.json"
    inbox_data = json_read(inbox_file, {"agent": agent, "has_unread": False, "messages": [], "since": _now_iso()})
    if isinstance(inbox_data, list):
        inbox_data = {"agent": agent, "has_unread": True, "messages": inbox_data, "since": _now_iso()}
    inbox = Inbox.from_dict(inbox_data)
    inbox.has_unread = True
    inbox.messages.append(msg_dict)
    json_write(inbox_file, inbox.to_dict())
    handler._send_json({"status": "ok", "id": msg_dict["id"], "state": "pending", "msg_id": msg_dict["id"]})


def handle_agent_unread(handler, agent: str):
    """GET /api/agents/<agent>/unread — 指定 agent 的未读计数（java 对等面）。

    与 GET /api/inbox/<agent> 的 unread 字段同源（共用 _count_unread）。
    """
    from lib.api.handlers_system import _reload_store_config
    _reload_store_config(handler)  # 含 D2/D15 内置身份合并
    if not validate_agent_name_or_404(handler, agent):
        return
    inbox, _ = _read_inbox_file(handler, agent)
    if inbox is None:
        handler._send_json({"agent": agent, "unread": 0})
        return
    handler._send_json({"agent": agent, "unread": _count_unread(inbox)})
