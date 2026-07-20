"""GET/POST /api/workflows — registry 摘要与 CRUD。"""

from __future__ import annotations

import re

from lib.workflow.registry import get_workflow, load_registry, save_registry


def handle_workflows_list(handler):
    reg = load_registry(handler.data_dir)
    items = []
    for wf_id, wf in (reg.get("workflows") or {}).items():
        items.append({
            "id": wf_id,
            "version": wf.get("version"),
            "display": wf.get("display"),
            "mode": wf.get("mode"),
            "task_types": wf.get("task_types") or [],
            "tags": wf.get("tags") or [],
            "ui": wf.get("ui"),
            "phase_count": len(wf.get("phases") or []),
            "gate_count": len(wf.get("gates") or []),
        })
    handler._send_json({
        "status": "ok",
        "version": reg.get("version"),
        "updated_at": reg.get("updated_at"),
        "workflows": items,
    })


def handle_workflow_get(handler, workflow_id: str):
    reg = load_registry(handler.data_dir)
    wf = get_workflow(reg, workflow_id)
    if not wf:
        handler._send_json({"status": "error", "error": "not_found"}, 404)
        return
    handler._send_json({
        "status": "ok",
        "workflow_id": workflow_id,
        "workflow": wf,
    })


def _valid_id(wf_id: str) -> bool:
    return bool(wf_id and re.match(r"^[a-z][a-z0-9_]{1,63}$", wf_id))


def handle_workflow_save(handler, workflow_id: str):
    """POST /api/workflows/{id} — 创建或更新 workflow 定义。"""
    body = handler._read_post_body()
    wf = body.get("workflow")
    if not isinstance(wf, dict):
        handler._send_json({"status": "error", "error": "workflow object required"}, 400)
        return
    wf_id = (wf.get("id") or workflow_id or "").strip()
    if not _valid_id(wf_id):
        handler._send_json({"status": "error", "error": "invalid workflow id"}, 400)
        return
    wf["id"] = wf_id
    reg = load_registry(handler.data_dir)
    workflows = reg.setdefault("workflows", {})
    created = wf_id not in workflows
    workflows[wf_id] = wf
    save_registry(handler.data_dir, reg)
    handler._send_json({"status": "ok", "workflow_id": wf_id, "created": created})


def handle_workflow_delete(handler, workflow_id: str):
    """POST /api/workflows/{id}/delete — 删除 workflow。"""
    if not _valid_id(workflow_id):
        handler._send_json({"status": "error", "error": "invalid id"}, 400)
        return
    reg = load_registry(handler.data_dir)
    workflows = reg.get("workflows") or {}
    if workflow_id not in workflows:
        handler._send_json({"status": "error", "error": "not_found"}, 404)
        return
    del workflows[workflow_id]
    reg["workflows"] = workflows
    save_registry(handler.data_dir, reg)
    handler._send_json({"status": "ok", "deleted": workflow_id})
