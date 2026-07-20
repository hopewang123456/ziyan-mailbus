"""mailbus 外部工作流工具 — Coze / Dify / webhook。

根目录：{mailbus_root}/external-tools/
  registry.json   — 工具注册
  grants.json     — agent 授权
  adapters/<agent>/<tool>.json — 配对适配
  logs/           — 调用日志

编制内 agent 通过 tool id 调用；工具不注册为 config.agents 成员。
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from .utils import json_read, _now_iso

TZ_CN = timezone(timedelta(hours=8))


def mailbus_root(data_dir: str) -> str:
    return os.path.dirname(os.path.abspath(data_dir))


def external_tools_dir(data_dir: str) -> str:
    env = os.environ.get("MAILBUS_EXTERNAL_TOOLS_DIR", "").strip()
    if env:
        return env
    root = mailbus_root(data_dir)
    v3 = os.path.join(root, "access", "external-tools")
    if os.path.isdir(v3):
        return v3
    legacy = os.path.join(root, "external-tools")
    return legacy


def _read_json(path: str) -> dict:
    return json_read(path, {}) if os.path.isfile(path) else {}


def _resolve_file(base_dir: str, name: str, example_name: str) -> str:
    primary = os.path.join(base_dir, name)
    if os.path.isfile(primary):
        return primary
    return os.path.join(base_dir, example_name)


def load_registry(data_dir: str) -> dict:
    base = external_tools_dir(data_dir)
    if os.path.isdir(base):
        return _read_json(_resolve_file(base, "registry.json", "registry.example.json"))
    # legacy
    legacy = os.path.join(data_dir, "config", "external-tools.json")
    if os.path.isfile(legacy):
        return _read_json(legacy)
    return _read_json(os.path.join(data_dir, "config", "external-tools.example.json"))


def load_grants(data_dir: str) -> dict:
    base = external_tools_dir(data_dir)
    if os.path.isdir(base):
        g = _read_json(_resolve_file(base, "grants.json", "grants.example.json"))
        if g.get("agent_grants"):
            return g
    reg = load_registry(data_dir)
    return {"agent_grants": reg.get("agent_grants") or {}}


def load_external_tools_config(data_dir: str) -> dict:
    """合并 registry + grants，供 CLI / 旧调用方使用。"""
    registry = load_registry(data_dir)
    grants = load_grants(data_dir)
    merged = dict(registry)
    merged["agent_grants"] = grants.get("agent_grants") or {}
    merged["_paths"] = {
        "external_tools_dir": external_tools_dir(data_dir),
        "registry": _resolve_file(external_tools_dir(data_dir), "registry.json", "registry.example.json"),
        "grants": _resolve_file(external_tools_dir(data_dir), "grants.json", "grants.example.json"),
    }
    return merged


def adapter_path(data_dir: str, agent_id: str, tool_id: str) -> str:
    return os.path.join(external_tools_dir(data_dir), "adapters", agent_id, f"{tool_id}.json")


def load_adapter(data_dir: str, agent_id: str, tool_id: str) -> Optional[dict]:
    path = adapter_path(data_dir, agent_id, tool_id)
    if not os.path.isfile(path):
        return None
    data = _read_json(path)
    if not data.get("enabled", True):
        return None
    return data


def list_adapters_for_agent(data_dir: str, agent_id: str) -> list[dict]:
    base = os.path.join(external_tools_dir(data_dir), "adapters", agent_id)
    if not os.path.isdir(base):
        return []
    out = []
    for name in sorted(os.listdir(base)):
        if not name.endswith(".json"):
            continue
        data = _read_json(os.path.join(base, name))
        if data:
            out.append(data)
    return out


def list_tools_for_agent(data_dir: str, agent_id: str) -> list[dict]:
    registry = load_registry(data_dir)
    grants = load_grants(data_dir).get("agent_grants") or {}
    allowed = set(grants.get(agent_id, []))
    tools = []
    for t in registry.get("tools") or []:
        if t.get("id") not in allowed:
            continue
        entry = dict(t)
        adapter = load_adapter(data_dir, agent_id, t["id"])
        if adapter:
            entry["adapter"] = {
                "description": adapter.get("description"),
                "output_path_template": adapter.get("output_path_template"),
                "post_invoke": adapter.get("post_invoke"),
            }
        tools.append(entry)
    return tools


def _resolve_env(key: Optional[str]) -> str:
    if not key:
        return ""
    if key.startswith("env:"):
        return os.environ.get(key[4:], "")
    return os.environ.get(key, "")


def _tool_by_id(registry: dict, tool_id: str) -> Optional[dict]:
    for t in registry.get("tools") or []:
        if t.get("id") == tool_id:
            return t
    return None


def agent_may_invoke(data_dir: str, agent_id: str, tool_id: str) -> bool:
    grants = load_grants(data_dir).get("agent_grants") or {}
    return tool_id in (grants.get(agent_id) or [])


def apply_input_map(adapter: Optional[dict], inputs: dict[str, Any]) -> dict[str, Any]:
    if not adapter or not adapter.get("input_map"):
        return dict(inputs)
    mapped: dict[str, Any] = {}
    for target_field, source_key in adapter["input_map"].items():
        if source_key in inputs:
            mapped[target_field] = inputs[source_key]
    return mapped


def render_output_path(template: str, inputs: dict[str, Any]) -> str:
    def repl(m: re.Match) -> str:
        key = m.group(1)
        return str(inputs.get(key, m.group(0)))

    return re.sub(r"\{(\w+)\}", repl, template)


def _log_dir(data_dir: str) -> str:
    base = external_tools_dir(data_dir)
    custom = os.path.join(base, "logs")
    if os.path.isdir(base):
        return custom
    return os.path.join(data_dir, "logs", "external-tools")


def _log_invocation(data_dir: str, record: dict) -> None:
    log_dir = _log_dir(data_dir)
    os.makedirs(log_dir, exist_ok=True)
    day = datetime.now(TZ_CN).strftime("%Y-%m-%d")
    path = os.path.join(log_dir, f"{day}.jsonl")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _http_post_json(url: str, payload: dict, headers: dict, timeout: int) -> tuple[int, dict | str]:
    from .n8n.wsl_bridge import post_json_with_wsl_fallback

    return post_json_with_wsl_fallback(url, payload, headers, timeout=timeout)


def invoke_tool(
    data_dir: str,
    *,
    agent_id: str,
    tool_id: str,
    inputs: dict[str, Any],
    dry_run: bool = False,
) -> dict:
    """调用外部工具；自动加载 adapters/<agent>/<tool>.json 做 input_map。"""
    registry = load_registry(data_dir)
    if not agent_may_invoke(data_dir, agent_id, tool_id):
        return {
            "ok": False,
            "error": "forbidden",
            "message": f"agent {agent_id} 无权调用 tool {tool_id}",
        }

    tool = _tool_by_id(registry, tool_id)
    if not tool:
        return {"ok": False, "error": "not_found", "message": f"unknown tool {tool_id}"}

    adapter = load_adapter(data_dir, agent_id, tool_id)
    mapped_inputs = apply_input_map(adapter, inputs)
    defaults = registry.get("defaults") or {}
    timeout = int(defaults.get("timeout_seconds", 120))
    started = _now_iso()

    output_path = None
    if adapter and adapter.get("output_path_template"):
        output_path = render_output_path(adapter["output_path_template"], inputs)

    if dry_run:
        out = {
            "ok": True,
            "dry_run": True,
            "tool_id": tool_id,
            "agent_id": agent_id,
            "provider": tool.get("provider"),
            "inputs": inputs,
            "mapped_inputs": mapped_inputs,
            "adapter": adapter.get("description") if adapter else None,
            "output_path": output_path,
            "message": "接入口已就绪；填写 registry.json、grants.json 与 env 后将发起真实请求",
        }
        _log_invocation(data_dir, {"at": started, **out})
        return out

    provider = tool.get("provider")
    kind = tool.get("kind")

    try:
        if provider == "dify" and kind == "workflow":
            result = _invoke_dify_workflow(registry, tool, mapped_inputs, timeout)
        elif provider == "coze" and kind == "bot":
            result = _invoke_coze_bot(registry, tool, mapped_inputs, timeout)
        elif provider == "webhook" and kind == "webhook":
            result = _invoke_webhook(tool, mapped_inputs, timeout)
        elif provider == "comfyui" and kind in ("txt2img", "workflow", "image"):
            result = _invoke_comfyui(tool, mapped_inputs, timeout, data_dir)
        else:
            result = {"ok": False, "error": "unsupported", "message": f"{provider}/{kind}"}
    except Exception as exc:
        result = {"ok": False, "error": "exception", "message": str(exc)}

    result.setdefault("tool_id", tool_id)
    result.setdefault("agent_id", agent_id)
    result["invoked_at"] = started
    result["mapped_inputs"] = mapped_inputs
    if output_path:
        result["output_path"] = output_path
    if adapter:
        result["post_invoke"] = adapter.get("post_invoke", "write_file")
    _log_invocation(data_dir, result)
    return result


def _invoke_dify_workflow(registry: dict, tool: dict, inputs: dict, timeout: int) -> dict:
    providers = registry.get("providers") or {}
    dify = providers.get("dify") or {}
    base = _resolve_env(dify.get("base_url_env", "DIFY_BASE_URL"))
    api_key = _resolve_env(dify.get("api_key_env", "DIFY_API_KEY"))
    wf_id = tool.get("workflow_id", "")
    if not base or not api_key or wf_id.startswith("REPLACE"):
        return {
            "ok": False,
            "error": "not_configured",
            "message": "设置 DIFY_BASE_URL、DIFY_API_KEY 与 registry 中 workflow_id",
        }
    url = f"{base.rstrip('/')}/v1/workflows/run"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"inputs": inputs, "response_mode": "blocking", "user": "mailbus"}
    status, body = _http_post_json(url, payload, headers, timeout)
    return {"ok": 200 <= status < 300, "status": status, "provider": "dify", "body": body}


def _invoke_coze_bot(registry: dict, tool: dict, inputs: dict, timeout: int) -> dict:
    providers = registry.get("providers") or {}
    coze = providers.get("coze") or {}
    base = _resolve_env(coze.get("base_url_env", "COZE_API_BASE"))
    token = _resolve_env(coze.get("api_key_env", "COZE_API_TOKEN"))
    bot_id = tool.get("bot_id", "")
    if not base or not token or bot_id.startswith("REPLACE"):
        return {
            "ok": False,
            "error": "not_configured",
            "message": "设置 COZE_API_BASE、COZE_API_TOKEN 与 registry 中 bot_id",
        }
    url = f"{base.rstrip('/')}/v3/chat"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    query = inputs.get("query") or json.dumps(inputs, ensure_ascii=False)
    payload = {
        "bot_id": bot_id,
        "user_id": "mailbus",
        "stream": False,
        "additional_messages": [{"role": "user", "content": query, "content_type": "text"}],
    }
    status, body = _http_post_json(url, payload, headers, timeout)
    return {"ok": 200 <= status < 300, "status": status, "provider": "coze", "body": body}


def _invoke_webhook(tool: dict, inputs: dict, timeout: int) -> dict:
    url = _resolve_env(tool.get("url_env"))
    secret = _resolve_env(tool.get("secret_env"))
    if not url:
        return {"ok": False, "error": "not_configured", "message": "设置 webhook url_env"}
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Mailbus-Secret"] = secret
    status, body = _http_post_json(url, inputs, headers, timeout)
    return {"ok": 200 <= status < 300, "status": status, "provider": "webhook", "body": body}


def _invoke_comfyui(tool: dict, inputs: dict, timeout: int, data_dir: str = "") -> dict:
    from .comfyui.client import generate_txt2img
    from .gpu_coordinator import _load_store_config, acquire_gpu, release_gpu

    store_cfg = _load_store_config(data_dir) if data_dir else None
    acq = acquire_gpu("comfyui", store_cfg)
    if not acq.get("ok") and not acq.get("skipped"):
        return {
            "ok": False,
            "error": acq.get("error") or "gpu_busy",
            "message": acq.get("message") or "GPU 被占用",
            "gpu": acq,
        }
    try:
        base_env = tool.get("base_url_env") or "COMFYUI_BASE_URL"
        base = _resolve_env(base_env) or None
        out = generate_txt2img(inputs, base_url=base, timeout=timeout)
        out.setdefault("provider", "comfyui")
        if acq.get("steps"):
            out["gpu_acquire"] = acq
        return out
    finally:
        rel = release_gpu("comfyui", store_cfg)
        if rel.get("steps"):
            pass  # logged via invocation record if needed
