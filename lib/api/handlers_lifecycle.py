"""API: discovery, framework/role enable, chain budget, align."""
from __future__ import annotations

from lib.application.align_store import align_store_from_registry
from lib.application.chain_route import apply_ollama_decision, ensure_llm_or_prompt, load_budget
from lib.application.discover_agents import save_report
from lib.application.lifecycle import (
    disable_framework,
    enable_framework,
    set_role_enabled,
)
from lib.application.queries import active_agents
from lib.adapters.locale.errors_zh import message_zh
from lib.infra.utils import json_read


def handle_discover(handler):
    report = save_report(handler.data_dir)
    handler._send_json({"status": "ok", **report})


def handle_align(handler):
    body = {}
    try:
        body = handler._read_post_body() or {}
    except Exception:
        body = {}
    expect = int(body.get("expect_min") or 13)
    result = align_store_from_registry(handler.data_dir, expect_min=expect)
    status = "ok" if result.get("ok") else "warn"
    handler._send_json({"status": status, **result})


def handle_active_agents(handler):
    active = active_agents(handler.data_dir)
    handler._send_json({
        "status": "ok",
        "agents": [
            {"id": k, **{kk: vv for kk, vv in v.items() if kk != "push"}}
            for k, v in active.items()
        ],
    })


def handle_framework_enable(handler, framework_id: str):
    body = handler._read_post_body() or {}
    result = enable_framework(
        handler.data_dir,
        framework_id,
        mount_mode=str(body.get("mount_mode") or "container"),
        root_path=str(body.get("root_path") or ""),
        health_url=str(body.get("health_url") or ""),
        start_cmd=body.get("start_cmd"),
    )
    code = 200 if result.get("ok") else 400
    if result.get("error_code") and not result.get("ok"):
        result = {**result, "message_zh": message_zh(str(result["error_code"]), str(result.get("error") or ""))}
    handler._send_json({"status": "ok" if result.get("ok") else "error", **result}, code)


def handle_framework_disable(handler, framework_id: str):
    body = handler._read_post_body() or {}
    result = disable_framework(
        handler.data_dir,
        framework_id,
        confirm_fail_tasks=bool(body.get("confirm")),
        stop_cmd=body.get("stop_cmd"),
    )
    code = 200 if result.get("ok") else (409 if result.get("needs_confirm") else 400)
    if result.get("error_code") and not result.get("ok"):
        result = {**result, "message_zh": message_zh(str(result["error_code"]), str(result.get("error") or result.get("message") or ""))}
    handler._send_json({"status": "ok" if result.get("ok") else "error", **result}, code)


def handle_role_enable(handler, agent_id: str):
    body = handler._read_post_body() or {}
    enabled = body.get("enabled")
    if enabled is None:
        enabled = True
    result = set_role_enabled(handler.data_dir, agent_id, bool(enabled))
    code = 200 if result.get("ok") else 400
    if result.get("error_code") and not result.get("ok"):
        result = {**result, "message_zh": message_zh(str(result["error_code"]), str(result.get("error") or ""))}
    handler._send_json({"status": "ok" if result.get("ok") else "error", **result}, code)


def handle_chain_budget(handler):
    cfg = json_read(f"{handler.data_dir}/config.json", {})
    if handler.command == "POST":
        body = handler._read_post_body() or {}
        if "use_ollama" in body:
            use = body.get("use_ollama")
            if use is None or use == "null":
                use = None
            state = apply_ollama_decision(handler.data_dir, cfg, use_ollama=use)
            handler._send_json({"status": "ok", "budget": state})
            return
    state = load_budget(handler.data_dir, cfg)
    llm = ensure_llm_or_prompt(cfg)
    handler._send_json({"status": "ok", "budget": state, "llm": llm})


def handle_mailbus_token(handler):
    """GET: ensure + masked status. POST rotate: returns plaintext once."""
    from lib.application.mailbus_token import (
        client_context_from_handler,
        ensure_token,
        resolve_token,
        rotate_token,
    )
    from lib.adapters.locale.errors_zh import message_zh

    ctx = client_context_from_handler(handler)
    if handler.command == "POST":
        result = rotate_token(
            handler.data_dir,
            ctx,
            config={"auth": {"exempt_cidrs": getattr(handler, "exempt_cidrs", [])}},
        )
        if not result.get("ok"):
            handler._send_json({
                "status": "error",
                **result,
                "message_zh": message_zh(str(result.get("error_code") or "unauthorized")),
            }, 401)
            return
        # refresh handler class token for subsequent requests in-process
        try:
            from lib.api.base import MailbusAPIHandler

            MailbusAPIHandler.auth_token = result.get("token")
        except Exception:
            pass
        handler._send_json({"status": "ok", "token": result["token"], "message": "rotated_once"})
        return

    tok = ensure_token(handler.data_dir)
    masked = (tok[:4] + "…" + tok[-4:]) if tok and len(tok) > 8 else "***"
    handler._send_json({
        "status": "ok",
        "configured": bool(resolve_token(handler.data_dir)),
        "token_masked": masked,
        "hint": "跨机写操作使用 Authorization: Bearer <token>；本机可免 token",
    })


def handle_agent_instance_load_roles(handler):
    """POST /api/agent-instances/load-roles — 扫描 Members/约定目录，挂到实例下。"""
    from lib.adapters.config.instance_roles import load_roles_for_instance

    body = handler._read_post_body() or {}
    iid = str(body.get("instance_id") or "").strip()
    if not iid:
        handler._send_json({"status": "error", "error": "instance_id required"}, 400)
        return
    try:
        result = load_roles_for_instance(handler.data_dir, iid)
        handler._send_json({"status": "ok", **result})
    except ValueError as exc:
        handler._send_json({"status": "error", "error": str(exc)}, 400)
    except Exception as exc:
        handler._send_json({"status": "error", "error": str(exc)}, 500)


def handle_agent_instance_upsert(handler):
    """POST /api/agent-instances — 新建/更新 Agent 实例卡（不含角色）。"""
    from lib.adapters.config.instance_roles import upsert_instance

    body = handler._read_post_body() or {}
    fields = body.get("fields") if isinstance(body.get("fields"), dict) else body
    iid = str(body.get("instance_id") or fields.get("id") or "").strip() or None
    try:
        result = upsert_instance(handler.data_dir, fields, instance_id=iid)
        handler._send_json({"status": "ok", **result})
    except ValueError as exc:
        handler._send_json({"status": "error", "error": str(exc)}, 400)
    except Exception as exc:
        handler._send_json({"status": "error", "error": str(exc)}, 500)


def handle_agent_instance_discover(handler):
    """POST /api/agent-instances/discover — 仅预览将加载的角色（不写盘）。"""
    from lib.adapters.config.instance_roles import discover_roles_for_instance
    from lib.infra.utils import json_read
    import os

    body = handler._read_post_body() or {}
    iid = str(body.get("instance_id") or "").strip()
    cfg = json_read(os.path.join(handler.data_dir, "config.json"), {})
    inst = (cfg.get("agent_instances") or {}).get(iid)
    if not isinstance(inst, dict):
        handler._send_json({"status": "error", "error": f"unknown instance: {iid}"}, 404)
        return
    roles = discover_roles_for_instance(inst)
    handler._send_json({"status": "ok", "instance_id": iid, "roles": roles, "count": len(roles)})


def handle_agent_scan(handler):
    """POST /api/agents/scan — 验证实例安装路径并扫描原生目录资产。

    body: { instance_id, framework?, install_path, run_target, distro?, agent_id? }
    运行环境字段（install_path/run_target/distro/gate_passed）写回**实例级**；
    角色级 enabled 是「退役/工作」手动开关，不由扫描覆盖。
    agent_id 可选：指定扫描代表角色；缺省用实例首角色。
    """
    import os

    from lib.adapters.config.native_scan import scan_agent_assets
    from lib.application.commands.commands import save_config
    from lib.infra.utils import json_read

    body = {}
    try:
        body = handler._read_post_body() or {}
    except Exception:
        body = {}
    instance_id = str(body.get("instance_id") or "").strip()
    agent_id = str(body.get("agent_id") or "").strip()
    if not instance_id and not agent_id:
        handler._send_json({"status": "error", "error": "instance_id required"}, 400)
        return
    framework = str(body.get("framework") or "").strip()
    install_path = str(body.get("install_path") or "").strip()
    run_target = str(body.get("run_target") or "windows").strip()
    distro = str(body.get("distro") or "auto").strip()

    from lib.adapters.frameworks.framework_discovery import (
        clear_framework_discovery_cache,
        framework_run_targets,
    )

    cfg_path = os.path.join(handler.data_dir, "config.json")
    cfg = json_read(cfg_path, {})
    agents = cfg.get("agents") or {}
    instances = cfg.get("agent_instances") or {}

    if instance_id and instance_id in instances:
        iid = instance_id
        inst = instances[iid]
    elif agent_id and agent_id in agents:
        # 兼容旧调用：从角色反查实例
        iid = str(agents[agent_id].get("instance_id") or "").strip()
        inst = instances.get(iid) if iid and iid in instances else {}
        if not inst:
            handler._send_json({"status": "error", "error": f"unknown instance for agent: {agent_id}"}, 404)
            return
    else:
        handler._send_json({"status": "error", "error": f"unknown instance: {instance_id or agent_id}"}, 404)
        return

    # 扫描代表角色：优先显式 agent_id，否则实例首角色
    scan_agent = agent_id or (inst.get("role_ids") or [None])[0]
    if not scan_agent:
        handler._send_json({"status": "error", "error": "instance has no roles; load roles first"}, 400)
        return

    fw = framework or str(inst.get("type") or "").strip()
    valid_targets = framework_run_targets(fw)
    if run_target not in valid_targets:
        run_target = valid_targets[0] if valid_targets else "windows"

    result = scan_agent_assets(
        fw,
        scan_agent,
        install_path,
        data_dir=handler.data_dir,
        run_target=run_target,
    )

    # path_existence_gate：目标端路径存在才视为可监测；写实例级，不碰角色级 enabled
    gate_passed = bool(result.get("gate", {}).get("passed"))
    inst = dict(inst)
    inst["install_path"] = install_path
    inst["run_target"] = run_target
    inst["distro"] = distro or "auto"
    inst["gate_passed"] = gate_passed
    inst.setdefault("enabled", True)
    instances[iid] = inst
    cfg["agent_instances"] = instances
    try:
        save_config(cfg_path, cfg)
        clear_framework_discovery_cache()
    except Exception as exc:
        handler._send_json({"status": "error", "error": f"save failed: {exc}"}, 500)
        return

    all_disabled = all(
        not (isinstance(a, dict) and a.get("enabled")) for a in agents.values()
    )
    handler._send_json({
        "status": "ok",
        "instance_id": iid,
        "scan_agent": scan_agent,
        **result,
        "install_path": install_path,
        "run_target": run_target,
        "distro": distro or "auto",
        "gate_passed": gate_passed,
        "enabled": gate_passed,
        "first_configure": all_disabled,
        "hint": "扫描结果来自 _path-map.json junctions.mount_points + 框架约定；运行环境字段已写回实例级",
    })
