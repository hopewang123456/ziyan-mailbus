"""A2A Agent Card / 入站任务 HTTP handlers。"""
from __future__ import annotations

import json
import os

from lib.api.handlers_tasks import create_task_from_envelope
from lib.transport.agent_card_cache import AgentCardCache, load_registry
from lib.transport.a2a_mapper import from_a2a_task_create
from lib.utils import json_read


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


def _stream_a2a_task_progress(handler, rpc_id, wire_task: dict) -> None:
    """SSE：首帧后按 FSM 推送 TaskStatusUpdateEvent 直至 terminal / 超时。"""
    from lib.transport.a2a_stream import build_status_update_result, iter_stream_events

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


def handle_a2a_rpc(handler, agent_id: str):
    """POST /api/a2a/rpc/{agent_id} — JSON-RPC 2.0 入站代理（SendMessage / SendStreamingMessage / GetTask / CancelTask）。"""
    body = handler._read_post_body()
    method = body.get("method") or ""
    params = body.get("params") or {}
    rpc_id = body.get("id")

    def _rpc_result(result: dict, *, http_status: int = 200):
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
        from lib.tracker import TaskTracker
        from lib.composition import build_orchestration
        from lib.transport.a2a_mapper import to_a2a_hub_task

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
        from lib.tracker import TaskTracker
        from lib.adapters.orchestration.task_fsm import apply_cancel

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
            json_write = __import__("lib.utils", fromlist=["json_write"]).json_write
            json_write(tracker._task_path(t.get("task_id")), t)
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
            handler._send_sse_start(http_status=status)
            handler._send_sse_jsonrpc(rpc_id, wire_task)
            _stream_a2a_task_progress(handler, rpc_id, wire_task)
            return
        from lib.transport.a2a_stream import aggregate_stream_task

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
