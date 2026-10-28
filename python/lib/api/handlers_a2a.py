"""A2A Agent Card / 入站任务 HTTP handlers。"""
from __future__ import annotations

import json
import os

from lib.api.handlers_tasks import create_task_from_envelope
from lib.core.a2a.agent_card_cache import AgentCardCache, load_registry
from lib.core.a2a.a2a_mapper import from_a2a_task_create
from lib.infra.utils import json_read

# M2d-b1：A2A 0.3 协议方法名 → 0.2 内部名 alias（与 java SDK 面对等，双名兼容）
_A2A_METHOD_ALIASES = {
    "message/send": "SendMessage",
    "message/stream": "SendStreamingMessage",
    "tasks/get": "GetTask",
    "tasks/cancel": "CancelTask",
}

# M2d-b2b：SDK 面 wire 形状（java A2aSdkBridge.wireToSdkTask / Gson 序列化 Task record 同款）
_SDK_STATE = {
    "submitted": "TASK_STATE_SUBMITTED",
    "working": "TASK_STATE_WORKING",
    "input-required": "TASK_STATE_INPUT_REQUIRED",
    "completed": "TASK_STATE_COMPLETED",
    "failed": "TASK_STATE_FAILED",
    "canceled": "TASK_STATE_CANCELED",
    "rejected": "TASK_STATE_REJECTED",
}


def _to_sdk_task(wire: dict) -> dict:
    """mailbus wire task（0.2 形状）→ SDK 官方裸 Task 形状（无 task 包装）。"""
    from datetime import datetime, timezone

    metadata = wire.get("metadata") or {}
    mailbus = metadata.get("mailbus") or {}
    return {
        "id": wire.get("id"),
        "contextId": mailbus.get("taskId") or wire.get("id"),
        "status": {
            "state": _SDK_STATE.get(wire.get("status") or "", "TASK_STATE_UNSPECIFIED"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "artifacts": [],
        "history": [],
        "metadata": metadata,
    }


def handle_a2a_agent_card_list(handler):
    """GET /api/a2a/agent-cards"""
    registry = load_registry(handler.data_dir)
    items = []
    cache = AgentCardCache(data_dir=handler.data_dir)
    for agent_id in sorted(registry):
        card = cache.get(agent_id)
        if not card:
            continue
        meta = (card.get("metadata") or {}).get("mailbus") or {}
        items.append({
            "agent_id": agent_id,
            "name": card.get("name"),
            "functional_group": meta.get("functional_group"),
            "runtime": meta.get("runtime"),
            "has_a2a": bool(card.get("supportedInterfaces")),
        })
    handler._send_json({"status": "ok", "total": len(items), "items": items})


def handle_a2a_agent_card_get(handler, agent_id: str):
    """GET /api/a2a/agent-card/{id}"""
    cache = AgentCardCache(data_dir=handler.data_dir)
    card = cache.get(agent_id)
    if not card:
        handler._send_json({"error": "not_found"}, 404)
        return
    handler._send_json({"status": "ok", "agent_id": agent_id, "wire": card})


def handle_a2a_protocol_status(handler):
    """GET /api/a2a/protocol"""
    path = os.path.join(handler.data_dir, "config", "a2a-protocol.json")
    if not os.path.isfile(path):
        path = os.path.join(handler.data_dir, "..", "config", "a2a-protocol.json")
    doc = json_read(path, {})
    handler._send_json({"status": "ok", "protocol": doc})


def handle_a2a_tasks_create(handler):
    """POST /api/a2a/tasks — 外部 A2A SendMessage 注入为 mailbus 任务。"""
    body = handler._read_post_body()
    skills = body.get("skills")
    params = body.get("params") or body
    envelope = from_a2a_task_create(params, skills=skills)
    resp, status = create_task_from_envelope(handler.data_dir, envelope)
    if resp.get("status") == "ok":
        resp = {**resp, "source": "a2a_inbound", "envelope": envelope}
    handler._send_json(resp, status)


def _stream_a2a_task_progress(handler, rpc_id, wire_task: dict, wire_style: str = "legacy") -> None:
    """SSE：首帧后按 FSM 推送 TaskStatusUpdateEvent 直至 terminal / 超时。

    M2d-b2b：wire_style="sdk" 帧为 SDK TaskStatusUpdateEvent 形状
    （taskId/status.state=TASK_STATE_*/contextId/metadata，无 final——
    java A2aSdkBridge.statusEvent 同款；流结束由连接关闭表达）。
    """
    from lib.core.a2a.a2a_stream import build_status_update_result, iter_stream_events

    paths = {"inbox": os.path.join(handler.data_dir, "inbox")}
    a2a_task_id = wire_task.get("id") or ""
    for event in iter_stream_events(
        handler.data_dir,
        wire_task,
        agents=handler.agents,
        paths=paths,
    ):
        kind = event.get("kind")
        if kind == "heartbeat":
            handler._send_sse_comment()
            continue
        if kind != "update":
            continue
        hub = event["hub"]
        is_final = event["final"]
        if wire_style == "sdk":
            sdk = _to_sdk_task(hub)
            handler._send_sse_jsonrpc(rpc_id, {
                "taskId": sdk["id"],
                "contextId": sdk["contextId"],
                "status": sdk["status"],
                "metadata": sdk["metadata"],
            })
        else:
            handler._send_sse_jsonrpc(
                rpc_id,
                build_status_update_result(a2a_task_id, hub, final=is_final),
            )
        if is_final:
            break


def _create_a2a_wire_task(handler, agent_id: str, params: dict):
    """SendMessage / SendStreamingMessage 共用：创建 mailbus 任务并返回 wire Task。"""
    skills = None
    cache = AgentCardCache(data_dir=handler.data_dir)
    card = cache.get(agent_id)
    if card:
        skills = card.get("skills")
    envelope = from_a2a_task_create(params, skills=skills)
    resp, status = create_task_from_envelope(handler.data_dir, envelope)
    if resp.get("status") != "ok":
        return None, status, (-32602, resp.get("message") or resp.get("error", "create_failed"))
    task = resp.get("task") or {}
    chain = task.get("chain") or []
    step = chain[0] if chain else {}
    a2a_task_id = step.get("a2a_task_id") or task.get("task_id") or envelope["task_id"]
    wire_task = {
        "id": a2a_task_id,
        "status": "working",
        "metadata": {"mailbus": {"taskId": task.get("task_id"), "stepId": step.get("step_id")}},
    }
    return wire_task, status, None


def handle_a2a_rpc(handler, agent_id: str, wire_style: str = "legacy"):
    """POST /api/a2a/rpc/{agent_id} — JSON-RPC 2.0 入站代理（SendMessage / SendStreamingMessage / GetTask / CancelTask）。

    M2d-b1：同时接受 A2A 0.3 协议方法名（message/send 等 alias）；0.2 名称原样保留（向后兼容）。
    M2d-b2b：wire_style="sdk" 输出官方裸 Task 形状（java A2aSdkController 同款，
    供 /api/a2a/sdk/{agent_id} 端点）；legacy 保持 mailbus {"task": wire} 包装。
    """
    body = handler._read_post_body()
    method = _A2A_METHOD_ALIASES.get(body.get("method") or "", body.get("method") or "")
    params = body.get("params") or {}
    rpc_id = body.get("id")

    def _rpc_result(result: dict, *, http_status: int = 200):
        if wire_style == "sdk" and "task" in result:
            result = _to_sdk_task(result["task"])
            http_status = 200  # SDK 面统一 200（java 同；201 是 0.2 面创建语义）
        handler._send_json({"jsonrpc": "2.0", "id": rpc_id, "result": result}, http_status)

    def _rpc_error(code: int, message: str, *, http_status: int = 400):
        handler._send_json({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {"code": code, "message": message},
        }, http_status)

    if method == "SendMessage":
        wire_task, status, err = _create_a2a_wire_task(handler, agent_id, params)
        if err:
            _rpc_error(err[0], err[1], http_status=status)
            return
        _rpc_result({"task": wire_task}, http_status=status)
        return

    if method == "GetTask":
        tid = params.get("id") or params.get("taskId") or ""
        from lib.application.orchestration.tracker import TaskTracker
        from lib.composition import build_orchestration
        from lib.core.a2a.a2a_mapper import to_a2a_hub_task

        tracker = TaskTracker(handler.data_dir)
        task_doc = None
        for t in tracker.list_all():
            if t.get("task_id") == tid or t.get("id") == tid:
                task_doc = t
                break
            for step in t.get("chain") or []:
                if step.get("a2a_task_id") == tid:
                    task_doc = t
                    break
            if task_doc:
                break
        if not task_doc:
            _rpc_error(-32001, "task_not_found", http_status=404)
            return
        hq_items = build_orchestration(handler.data_dir).human_gate.load_queue().get("items") or []
        wire = to_a2a_hub_task(task_doc, tid, human_queue=hq_items)
        _rpc_result({"task": wire})
        return

    if method == "CancelTask":
        tid = params.get("id") or ""
        from lib.application.orchestration.tracker import TaskTracker
        # 跨层解耦：api→adapter 通过 composition 拿服务
        from lib.composition import apply_cancel

        tracker = TaskTracker(handler.data_dir)
        for t in tracker.list_all():
            match = t.get("task_id") == tid
            if not match:
                for step in t.get("chain") or []:
                    if step.get("a2a_task_id") == tid:
                        match = True
                        break
            if not match:
                continue
            apply_cancel(
                t, reason="a2a_cancel", data_dir=handler.data_dir, agents=handler.agents,
            )
            json_write = __import__("lib.infra.utils", fromlist=["json_write"]).json_write
            json_write(tracker._task_path(t.get("task_id")), t)
            if wire_style == "sdk":
                # SDK 面取消后返回官方 Task 形状（java bridge.onCancelTask 同语义）
                from lib.composition import build_orchestration  # 局部 import：函数级作用域
                from lib.core.a2a.a2a_mapper import to_a2a_hub_task

                hq_items = build_orchestration(handler.data_dir).human_gate.load_queue().get("items") or []
                _rpc_result({"task": to_a2a_hub_task(t, tid, human_queue=hq_items)})
            else:
                _rpc_result({"id": tid, "cancelled": True})
            return
        _rpc_error(-32001, "task_not_found", http_status=404)
        return

    if method == "SendStreamingMessage":
        wire_task, status, err = _create_a2a_wire_task(handler, agent_id, params)
        if err:
            _rpc_error(err[0], err[1], http_status=status)
            return
        accept = (handler.headers.get("Accept") or "").lower()
        if "text/event-stream" in accept or "application/json" not in accept:
            if wire_style == "sdk":
                status = 200  # SDK 面统一 200（java SseEmitter 同）
            handler._send_sse_start(http_status=status)
            if wire_style == "sdk":
                # SDK 面首帧=statusEvent 形状（java bridge 首帧同款）
                sdk = _to_sdk_task(wire_task)
                handler._send_sse_jsonrpc(rpc_id, {
                    "taskId": sdk["id"],
                    "contextId": sdk["contextId"],
                    "status": sdk["status"],
                    "metadata": sdk["metadata"],
                })
            else:
                handler._send_sse_jsonrpc(rpc_id, wire_task)
            _stream_a2a_task_progress(handler, rpc_id, wire_task, wire_style=wire_style)
            return
        from lib.core.a2a.a2a_stream import aggregate_stream_task

        paths = {"inbox": os.path.join(handler.data_dir, "inbox")}
        final_task = aggregate_stream_task(
            handler.data_dir,
            wire_task,
            rpc_id,
            agents=handler.agents,
            paths=paths,
        )
        _rpc_result({"task": final_task}, http_status=status)
        return

    _rpc_error(-32601, f"method_not_found: {method}", http_status=404)


def handle_a2a_sdk_rpc(handler, agent_id: str):
    """POST /api/a2a/sdk/{agent_id} — SDK 面（官方裸 Task wire 形状，java A2aSdkController 对等）。"""
    handle_a2a_rpc(handler, agent_id, wire_style="sdk")
