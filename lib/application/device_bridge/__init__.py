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
from lib.infra.utils import _now_iso, build_message, json_read, json_write, resolve_paths

_DEFAULTS = {
    "enabled": True,
    "default_wait_ms": 45000,
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


def deliver_and_wait(
    data_dir: str,
    agents: dict,
    agent_types: dict,
    device: dict,
    text: str,
    session_id: str,
    wait_ms: int,
    source: Optional[dict],
) -> dict:
    """通讯式一轮：投递 → push → 等回复。同步拿到则 ok，超时转 pending ticket。"""
    agent_id = str(device.get("agent_id") or "").strip()
    device_id = str(device.get("id") or "").strip()
    if agent_id not in agents:
        raise DeviceBridgeError("unknown_agent", 404, f"绑定 Agent 未注册: {agent_id}")
    if not (text or "").strip():
        raise DeviceBridgeError("empty_text", 400, "缺少 text")

    msg_id = _deliver_message(data_dir, agents, agent_types, device_id, agent_id, text, session_id, source)
    record_device_memory(data_dir, agent_id, device_id, text, msg_id, "user")

    deadline = time.time() + max(0, int(wait_ms)) / 1000.0
    while time.time() < deadline:
        reply = _read_reply(data_dir, agent_id, msg_id)
        if reply:
            record_device_memory(data_dir, agent_id, device_id, reply, msg_id, "assistant")
            return {
                "status": "ok",
                "reply": reply,
                "msg_id": msg_id,
                "agent_id": agent_id,
                "session_id": session_id,
            }
        time.sleep(0.5)

    ticket_id = uuid.uuid4().hex
    _store_ticket(data_dir, ticket_id, {
        "msg_id": msg_id,
        "agent_id": agent_id,
        "device_id": device_id,
        "session_id": session_id,
        "text": text,
        "source": source or {},
    })
    return {
        "status": "pending",
        "ticket_id": ticket_id,
        "poll_after_ms": 2000,
        "msg_id": msg_id,
        "agent_id": agent_id,
        "session_id": session_id,
    }


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
    return {
        "status": "pending",
        "ticket_id": ticket_id,
        "poll_after_ms": 2000,
        "msg_id": rec["msg_id"],
        "agent_id": rec["agent_id"],
    }
