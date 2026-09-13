"""Device Bridge — 外部设备（手机/眼镜上游）通讯式接入核心。

职责（与 intake_bridge / 工单流水线隔离）：
- 用设备 token（独立于 mailbus API token）鉴权并解析绑定 Agent；
- 通讯式一轮一答：投递 inbox → 即时 push → 等本轮回复 → HTTP 回传；
- 每请求新 session_id，不拼历史气泡进 prompt；
- 每轮双写 memory（SQLite 同步 + AgentMemory 后台降级），防 Agent 失忆；
- MVP 不建工单（tasks 另属 Phase 2）。
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from typing import Optional

from lib.domain.models import Inbox, MsgType, Priority
from lib.infra.clock import now_ts
from lib.infra.utils import _now_iso, build_message, json_read, json_write, resolve_paths

_DEFAULTS = {
    "enabled": True,
    "default_wait_ms": 8000,
    "write_memory": True,
    "devices": [],
}

# ticket_id → 待取结果记录（进程内；一轮一答短生命周期，重启可容忍丢失）
_TICKETS: dict[str, dict] = {}
_TICKETS_LOCK = threading.Lock()

# 记忆落盘由 API 层（可访问 adapters）注入；application 不直接 import adapters
_memory_recorder = None


def set_memory_recorder(fn) -> None:
    """注入记忆写入实现（signature: fn(data_dir, agent_id, device_id, text, msg_id, role)）。"""
    global _memory_recorder
    _memory_recorder = fn


class DeviceBridgeError(Exception):
    """设备桥业务错误，携带 HTTP 状态码。"""

    def __init__(self, code: str, status: int, detail: str = ""):
        super().__init__(detail or code)
        self.code = code
        self.status = status
        self.detail = detail


def load_bridge_config(data_dir: str) -> dict:
    """读取 config.json 的 mailbus_device_bridge，合并默认值。"""
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    raw = cfg.get("mailbus_device_bridge") or {}
    merged: dict = dict(_DEFAULTS)
    if isinstance(raw, dict):
        merged.update(raw)
    return merged


def _normalize_ip(addr: str) -> str:
    addr = (addr or "").strip().lower()
    if addr.startswith("::ffff:"):
        addr = addr.split("::ffff:", 1)[-1]
    return addr.split("%", 1)[0]


def resolve_device(bridge_cfg: dict, token: str, client_ip: str) -> Optional[dict]:
    """按 token 解析设备；可选校验 tailscale_ips。返回设备 dict 或 None。"""
    token = (token or "").strip()
    if not token or not bridge_cfg.get("enabled", True):
        return None
    ip = _normalize_ip(client_ip)
    for d in bridge_cfg.get("devices") or []:
        if not isinstance(d, dict):
            continue
        if d.get("enabled") is False:
            continue
        expected = (os.environ.get((d.get("token_env") or "").strip()) or "").strip()
        if not expected:
            expected = (d.get("token") or "").strip()
        if not expected or expected != token:
            continue
        ts_ips = [str(x).strip() for x in (d.get("tailscale_ips") or []) if str(x).strip()]
        if ts_ips and ip not in ts_ips:
            continue
        return d
    return None


def _read_reply(data_dir: str, agent_id: str, msg_id: str) -> str:
    """读取 replies/{agent}.json 中与 msg_id 关联的回复文本。"""
    path = os.path.join(data_dir, "replies", f"{agent_id}.json")
    if not os.path.isfile(path):
        return ""
    data = json_read(path, {})
    if not isinstance(data, dict):
        return ""
    mids = data.get("msg_ids") or []
    if msg_id and mids and msg_id not in mids:
        return ""
    return str(data.get("reply") or "").strip()


def _deliver_message(
    data_dir: str,
    agents: dict,
    agent_types: dict,
    device_id: str,
    agent_id: str,
    text: str,
    session_id: str,
    source: Optional[dict],
) -> str:
    """写 inbox + 即时 push，返回 msg_id。"""
    from_ = f"device:{device_id}"
    msg_dict = build_message(from_, agent_id, text, MsgType.NOTICE, Priority.NORMAL).to_dict()
    msg_dict["device_session_id"] = session_id
    msg_dict["device_source"] = source or {}
    msg_id = msg_dict["id"]

    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent_id}/inbox.json"
    inbox_data = json_read(
        inbox_file, {"agent": agent_id, "has_unread": False, "messages": [], "since": _now_iso()}
    )
    if isinstance(inbox_data, list):
        inbox_data = {"agent": agent_id, "has_unread": True, "messages": inbox_data, "since": _now_iso()}
    inbox = Inbox.from_dict(inbox_data)
    inbox.has_unread = True
    inbox.messages.append(msg_dict)
    json_write(inbox_file, inbox.to_dict())

    try:
        from lib.application.push.pusher import push_messages, resolve_cli_chain

        agent_cfg = agents.get(agent_id, {})
        cli_chain = resolve_cli_chain(agent_cfg, agent_types)
        if cli_chain:
            cli_cmds = [c[0] for c in cli_chain]
            from lib.application.orchestration.pipeline.task import should_auto_ack_message

            auto_ack = should_auto_ack_message(
                msg_dict, data_dir, agent_cfg.get("type", ""),
            )
            push_messages(
                data_dir, agent_id, [msg_dict], cli_cmd=cli_cmds, auto_ack=auto_ack,
            )
    except Exception:
        pass  # 推送失败不影响已写入；回复轮询会自然超时转 pending

    return msg_id


def record_device_memory(
    data_dir: str,
    agent_id: str,
    device_id: str,
    text: str,
    msg_id: str,
    role: str,
) -> None:
    """每轮落盘 memory。实现由 API 层注入（SQLite 同步 + AgentMemory 后台降级）。"""
    if _memory_recorder is None:
        return
    if not (text or "").strip():
        return
    cfg = json_read(os.path.join(data_dir, "config.json"), {})
    dbr = cfg.get("mailbus_device_bridge") or {}
    if dbr.get("write_memory", True) is False:
        return
    try:
        _memory_recorder(data_dir, agent_id, device_id, text, msg_id, role)
    except Exception:
        pass


def _store_ticket(data_dir: str, ticket_id: str, record: dict) -> None:
    record = dict(record)
    record["created_at"] = _now_iso()
    with _TICKETS_LOCK:
        _TICKETS[ticket_id] = record


def _load_ticket(ticket_id: str) -> Optional[dict]:
    with _TICKETS_LOCK:
        return _TICKETS.get(ticket_id)


def _inbox_msg_meta(data_dir: str, agent_id: str, msg_id: str) -> dict:
    """读取 inbox 中该 msg 的 status / pushed 信息，供 pending 诊断。"""
    paths = resolve_paths(data_dir)
    inbox_file = f"{paths['inbox']}/{agent_id}/inbox.json"
    data = json_read(inbox_file, {})
    msgs = data.get("messages") if isinstance(data, dict) else data
    if not isinstance(msgs, list):
        return {}
    for m in msgs:
        if isinstance(m, dict) and m.get("id") == msg_id:
            return {
                "inbox_status": m.get("status") or m.get("state") or "",
                "pushed_count": m.get("pushed_count") or 0,
                "api_stall_reason": m.get("api_stall_reason") or "",
            }
    return {}


def _pending_payload(
    data_dir: str,
    *,
    ticket_id: str,
    msg_id: str,
    agent_id: str,
    session_id: str,
) -> dict:
    meta = _inbox_msg_meta(data_dir, agent_id, msg_id)
    out = {
        "status": "pending",
        "ticket_id": ticket_id,
        "poll_after_ms": 2000,
        "msg_id": msg_id,
        "agent_id": agent_id,
        "session_id": session_id,
        **meta,
    }
    st = str(meta.get("inbox_status") or "").lower()
    if st == "failed":
        out["hint"] = (
            f"绑定 Agent「{agent_id}」CLI 推送失败（常见：Docker/Hermes 未就绪）。"
            "可改绑公开测试角色 test，并运行 tools/device_bridge_mock_agent.py；"
            "或修好 Agent 运行时后用 ticket 轮询 / SSE 等待。"
        )
    elif st in ("pending", "") and int(meta.get("pushed_count") or 0) == 0:
        out["hint"] = f"消息已入队，等待 Agent「{agent_id}」消费；也可用 GET /api/device/chat/{{ticket_id}} 轮询。"
    else:
        out["hint"] = f"等待 Agent「{agent_id}」回复超时；可用 ticket 继续轮询，或改用 stream=true SSE。"
    return out


def _emit_streaming_reply(on_event, reply: str, result: dict, *, step: int = 2, delay: float = 0.025) -> None:
    """SSE 流式：把完整回复按字符分片推 delta（打字机效果），最后推 ok。

    agent runtime（hermes/openclaw）CLI 是「跑完才吐完整回复」，本身非流式；
    这里在拿到全文后分片推送，给手机端逐字出现的体验，无需改 agent 侧。
    客户端断开时（on_event 抛 BrokenPipeError）直接终止分片。
    """
    try:
        on_event("reply_start", {
            "msg_id": result.get("msg_id"),
            "agent_id": result.get("agent_id"),
            "session_id": result.get("session_id"),
        })
        i = 0
        n = len(reply)
        while i < n:
            on_event("delta", {"delta": reply[i:i + step]})
            i += step
            if delay > 0 and i < n:
                time.sleep(delay)
        on_event("ok", result)
    except Exception:
        pass  # 客户端断开 / 写失败：终止流式


def deliver_and_wait(
    data_dir: str,
    agents: dict,
    agent_types: dict,
    device: dict,
    text: str,
    session_id: str,
    wait_ms: int,
    source: Optional[dict],
    on_event=None,
) -> dict:
    """通讯式一轮：投递 → push → 等回复。同步拿到则 ok，超时转 pending ticket。

    on_event: 可选回调 fn(event: str, data: dict)，供 SSE 推送（accepted / waiting / ok / pending）。
    """
    agent_id = str(device.get("agent_id") or "").strip()
    device_id = str(device.get("id") or "").strip()
    if agent_id not in agents:
        raise DeviceBridgeError("unknown_agent", 404, f"绑定 Agent 未注册: {agent_id}")
    if not (text or "").strip():
        raise DeviceBridgeError("empty_text", 400, "缺少 text")

    msg_id = _deliver_message(data_dir, agents, agent_types, device_id, agent_id, text, session_id, source)
    record_device_memory(data_dir, agent_id, device_id, text, msg_id, "user")
    if on_event:
        try:
            on_event("accepted", {
                "msg_id": msg_id,
                "agent_id": agent_id,
                "session_id": session_id,
                **_inbox_msg_meta(data_dir, agent_id, msg_id),
            })
        except Exception:
            pass

    deadline = now_ts() + max(0, int(wait_ms)) / 1000.0
    last_beat = 0.0
    while now_ts() < deadline:
        reply = _read_reply(data_dir, agent_id, msg_id)
        if reply:
            record_device_memory(data_dir, agent_id, device_id, reply, msg_id, "assistant")
            result = {
                "status": "ok",
                "reply": reply,
                "msg_id": msg_id,
                "agent_id": agent_id,
                "session_id": session_id,
            }
            if on_event:
                _emit_streaming_reply(on_event, reply, result)
            return result
        now = now_ts()
        if on_event and (now - last_beat) >= 1.5:
            last_beat = now
            try:
                on_event("waiting", {
                    "msg_id": msg_id,
                    "agent_id": agent_id,
                    "elapsed_ms": int((now - (deadline - max(0, int(wait_ms)) / 1000.0)) * 1000),
                    "remain_ms": max(0, int((deadline - now) * 1000)),
                    **_inbox_msg_meta(data_dir, agent_id, msg_id),
                })
            except Exception:
                pass
        time.sleep(0.4)

    ticket_id = uuid.uuid4().hex
    _store_ticket(data_dir, ticket_id, {
        "msg_id": msg_id,
        "agent_id": agent_id,
        "device_id": device_id,
        "session_id": session_id,
        "text": text,
        "source": source or {},
    })
    result = _pending_payload(
        data_dir,
        ticket_id=ticket_id,
        msg_id=msg_id,
        agent_id=agent_id,
        session_id=session_id,
    )
    if on_event:
        try:
            on_event("pending", result)
        except Exception:
            pass
    return result


def resolve_ticket(data_dir: str, ticket_id: str) -> dict:
    """轮询 ticket：若回复已到则 ok 并写 assistant 记忆，否则仍 pending。"""
    rec = _load_ticket(ticket_id)
    if not rec:
        raise DeviceBridgeError("ticket_not_found", 404, f"未知 ticket: {ticket_id}")
    reply = _read_reply(data_dir, rec["agent_id"], rec["msg_id"])
    if reply:
        record_device_memory(data_dir, rec["agent_id"], rec["device_id"], reply, rec["msg_id"], "assistant")
        return {
            "status": "ok",
            "reply": reply,
            "msg_id": rec["msg_id"],
            "agent_id": rec["agent_id"],
            "session_id": rec["session_id"],
        }
    return _pending_payload(
        data_dir,
        ticket_id=ticket_id,
        msg_id=rec["msg_id"],
        agent_id=rec["agent_id"],
        session_id=rec["session_id"],
    )
