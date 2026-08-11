"""Canonical ↔ Google A2A wire 映射。

规范：mail/docs/a2a-field-mapping.md
金样例：store/examples/golden-a2a-path-*.json
"""
from __future__ import annotations

import uuid
from typing import Any, Optional


_DOMAIN_TO_GROUP = {
    "product": "product",
    "quality": "engineering",
    "engineering": "engineering",
    "execution": "execution",
    "operations": "operations",
    "ops": "ops",
    "security": "security",
    "intake": "operations",
}


def to_a2a_message(dispatch: dict) -> dict:
    """canonical dispatch → JSON-RPC SendMessage params.message。"""
    parts: list[dict[str, Any]] = [{"text": dispatch.get("intent") or ""}]
    msg_file = dispatch.get("msg_file")
    if msg_file:
        parts.append(
            {
                "file": {
                    "uri": f"https://mailbus.example/artifacts/{msg_file.rsplit('/', 1)[-1]}",
                    "mimeType": "text/markdown",
                }
            }
        )
    return {
        "messageId": dispatch.get("message_id") or dispatch.get("msg_id"),
        "role": "ROLE_USER",
        "parts": parts,
        "metadata": {
            "mailbus": {
                "taskId": dispatch.get("task_id"),
                "stepId": dispatch.get("step_id"),
                "roleType": dispatch.get("role_type"),
                "toAgentId": dispatch.get("to_agent"),
                "protocolVersion": "mailbus-a2a/1",
            }
        },
    }


def _artifact_text(task: dict) -> str:
    chunks: list[str] = []
    for art in task.get("artifacts") or []:
        for part in art.get("parts") or []:
            if part.get("text"):
                chunks.append(str(part["text"]))
    return " ".join(chunks).strip()


def from_a2a_task(
    task: dict,
    *,
    task_id: str,
    step_id: str,
    agent: str,
    role_type: int,
) -> dict:
    """terminal A2A Task → canonical step-result。"""
    status = (task.get("status") or "").lower()
    conclusion = "done" if status == "completed" else "fail"
    if status == "input-required":
        conclusion = "pending"

    attachments = []
    for art in task.get("artifacts") or []:
        entry: dict[str, Any] = {"name": art.get("name")}
        if art.get("artifactId"):
            entry["a2a_artifact_id"] = art["artifactId"]
        attachments.append(entry)

    return {
        "task_id": task_id,
        "step_id": step_id,
        "agent": agent,
        "role_type": role_type,
        "conclusion": conclusion,
        "summary": task.get("statusMessage") or _artifact_text(task),
        "timestamp": task.get("lastModified") or task.get("updatedAt") or "",
        "source": "a2a_standard",
        "transport_used": "a2a_standard",
        "a2a_task_id": task.get("id"),
        "attachments": attachments,
    }


def to_a2a_resolve_message(
    *,
    task_id: str,
    step_id: str,
    agent_id: str,
    display_name: str,
    role_type: int,
    comment: str,
    hq_type: str = "a2a_input_required",
    hq_id: str = "",
    a2a_task_id: str = "",
) -> dict:
    """human-queue resolve → SendMessage（ROLE_AGENT）。"""
    return {
        "taskId": a2a_task_id,
        "message": {
            "messageId": str(uuid.uuid4()),
            "role": "ROLE_AGENT",
            "parts": [{"text": comment or ""}],
            "metadata": {
                "mailbus": {
                    "agentId": agent_id,
                    "displayName": display_name,
                    "roleType": role_type,
                    "hqType": hq_type,
                    "hqId": hq_id,
                    "taskId": task_id,
                    "stepId": step_id,
                    "protocolVersion": "mailbus-a2a/1",
                }
            },
        },
    }


def _parts_to_intent_and_artifacts(parts: list) -> tuple[str, list[dict]]:
    intent_chunks: list[str] = []
    artifacts_in: list[dict] = []
    for part in parts or []:
        if part.get("text"):
            intent_chunks.append(str(part["text"]))
        if part.get("file"):
            f = part["file"]
            artifacts_in.append({
                "kind": "file",
                "ref": f.get("uri") or f.get("name") or "",
                "label": f.get("name") or "attachment",
                "mime_type": f.get("mimeType"),
            })
        if part.get("data"):
            artifacts_in.append({
                "kind": "data",
                "ref": "inline",
                "label": "data",
                "data": part["data"],
            })
    return "\n".join(intent_chunks).strip(), artifacts_in


def from_a2a_task_create(params: dict, *, skills: Optional[list] = None) -> dict:
    """Google A2A SendMessage / 外部创建 → mailbus A2A Envelope。"""
    message = params.get("message") or params
    meta = (message.get("metadata") or {}).get("mailbus") or {}
    intent, artifacts_in = _parts_to_intent_and_artifacts(message.get("parts") or [])

    task_id = meta.get("taskId") or meta.get("task_id") or params.get("task_id") or ""
    if not task_id:
        task_id = f"ext-{uuid.uuid4().hex[:12]}"

    task_type = meta.get("taskType") or meta.get("task_type") or "custom"
    if skills and task_type == "custom":
        for sk in skills:
            tags = sk.get("tags") or []
            for tag in tags:
                if isinstance(tag, str) and tag.startswith("role_type:"):
                    task_type = "custom"
                    break

    envelope: dict[str, Any] = {
        "task_id": task_id,
        "intent": intent or meta.get("intent") or "external A2A task",
        "initiator": meta.get("initiator") or "external",
        "task_type": task_type,
        "tier": meta.get("tier") or "M",
        "mode": meta.get("mode") or "auto",
        "artifacts_in": artifacts_in,
        "extensions": dict(meta.get("extensions") or {}),
    }
    if meta.get("planned_chain"):
        envelope["mode"] = "explicit"
        envelope["planned_chain"] = meta["planned_chain"]
    if meta.get("constraints"):
        envelope["constraints"] = meta["constraints"]
    if meta.get("acceptance"):
        envelope["acceptance"] = meta["acceptance"]
    return envelope


def to_a2a_hub_task(
    task_doc: dict,
    a2a_task_id: str,
    *,
    human_queue: Optional[list] = None,
) -> dict:
    """mailbus task + FSM → 对外 A2A GetTask wire（含 final_acceptance 映射）。"""
    fsm = (task_doc.get("fsm") or {}).get("state", "executing")
    task_id = task_doc.get("task_id") or task_doc.get("id") or ""
    meta: dict[str, Any] = {
        "mailbus": {
            "taskId": task_id,
            "taskType": task_doc.get("task_type"),
            "tier": task_doc.get("tier"),
            "fsmState": fsm,
            "protocolVersion": "mailbus-a2a/1",
        }
    }

    status = "working"
    status_message = task_doc.get("intent") or ""

    pending_hq = None
    for item in human_queue or []:
        if item.get("status") != "pending":
            continue
        if item.get("task_id") != task_id:
            continue
        if item.get("type") in ("a2a_input_required", "final_acceptance", "plan_approval"):
            pending_hq = item
            break

    if pending_hq:
        status = "input-required"
        status_message = pending_hq.get("title") or status_message
        meta["mailbus"]["hqType"] = pending_hq.get("type")
        meta["mailbus"]["hqId"] = pending_hq.get("id")
        ctx = pending_hq.get("context") or {}
        if ctx.get("prompt"):
            status_message = ctx["prompt"]
    elif fsm == "accepting":
        status = "input-required"
        status_message = "等待终验确认"
        meta["mailbus"]["hqType"] = "final_acceptance"
    elif fsm in ("blocked", "paused"):
        status = "input-required"
        status_message = task_doc.get("pause_reason") or task_doc.get("error") or "blocked"
    elif fsm in ("succeeded", "success"):
        status = "completed"
    elif fsm == "failed":
        status = "failed"
    elif fsm == "cancelled":
        status = "canceled"
    elif fsm == "executing":
        status = "working"

    for step in task_doc.get("chain") or []:
        if isinstance(step, dict) and step.get("fsm_state") in ("queued", "running", "dispatched", "working"):
            meta["mailbus"]["stepId"] = step.get("step_id")
            if step.get("a2a_task_id"):
                a2a_task_id = step.get("a2a_task_id") or a2a_task_id
            break

    wire: dict[str, Any] = {
        "id": a2a_task_id or task_id,
        "status": status,
        "metadata": meta,
    }
    if status_message:
        wire["statusMessage"] = status_message
    return wire


def _skill_from_role(role_type: int, capability: str, role_zh: str = "") -> dict:
    return {
        "id": capability or f"role_type_{role_type}",
        "name": role_zh or capability or f"role {role_type}",
        "tags": [f"role_type:{role_type}"],
        "examples": [],
    }


def to_agent_card(
    agent_id: str,
    registry_entry: dict,
    *,
    display_name: str = "",
    functional_group: str = "",
    base_url: str = "https://mailbus.example",
) -> dict:
    """registry + profile → Google A2A AgentCard（wire camelCase）。"""
    runtime = registry_entry.get("runtime") or registry_entry.get("framework") or ""
    role_types = list(registry_entry.get("role_types") or [])
    capabilities = list(registry_entry.get("capabilities") or [])
    channels = registry_entry.get("channels") or {}
    a2a_on = (channels.get("a2a") or {}).get("enabled", True)
    endpoint = registry_entry.get("endpoint") or {}
    rpc_url = endpoint.get("base_url") or endpoint.get("rpc_url") or ""
    if not rpc_url and a2a_on and runtime == "hermes_profile":
        rpc_url = f"{base_url.rstrip('/')}/api/a2a/rpc/{agent_id}"

    interfaces = []
    if rpc_url and a2a_on:
        interfaces.append({
            "url": rpc_url,
            "protocolBinding": "JSONRPC",
            "protocolVersion": "1.0",
        })

    skills: list[dict] = []
    if len(role_types) <= 1:
        cap = capabilities[0] if capabilities else "general"
        skills.append(_skill_from_role(role_types[0] if role_types else 0, cap))
    else:
        for i, rt in enumerate(role_types):
            cap = capabilities[i] if i < len(capabilities) else f"role_type_{rt}"
            skills.append(_skill_from_role(rt, cap))

    name = display_name or registry_entry.get("display_name") or agent_id
    fg = functional_group or registry_entry.get("functional_group") or _DOMAIN_TO_GROUP.get(
        registry_entry.get("domain", ""), "engineering"
    )
    auth_scheme = (registry_entry.get("auth") or {}).get("scheme", "none")
    auth_schemes = ["Bearer"] if auth_scheme == "bearer" else []

    return {
        "name": name,
        "description": ", ".join(registry_entry.get("tags") or capabilities or [runtime]),
        "version": registry_entry.get("version") or "1.0.0",
        "supportedInterfaces": interfaces,
        "capabilities": {
            "streaming": bool((registry_entry.get("features") or {}).get("streaming")),
            "pushNotifications": bool((registry_entry.get("features") or {}).get("push_notifications")),
        },
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "skills": skills or [{"id": "general", "name": name, "tags": [fg], "examples": []}],
        "authentication": {"schemes": auth_schemes},
        "metadata": {
            "mailbus": {
                "agent_id": agent_id,
                "display_name": name,
                "role_types": role_types,
                "functional_group": fg,
                "runtime": runtime,
                "transport_default": "file_bus" if not a2a_on else "a2a_standard",
            }
        },
    }
