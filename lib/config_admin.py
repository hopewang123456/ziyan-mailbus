"""Mailbus 配置中心 — UI 读写 config.json 与 .env（脱敏）。"""

from __future__ import annotations

import copy
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .commands import save_config
from .config_schema import validate_config
from .env_bootstrap import load_mailbus_env
from .utils import json_read, json_write


def _agent_has_desktop_flag(agent_cfg: dict, agent_types: dict) -> bool:
    from .desktop_launch import agent_has_desktop

    return agent_has_desktop(agent_cfg, agent_types)

# 可在 Dashboard 编辑的 config.json 段
EDITABLE_SECTIONS = frozenset({
    "mailbus_internal_llm",
    "mailbus_workflow",
    "mailbus_automation",
    "mailbus_intake_bridge",
    "mailbus_codex",
    "mailbus_claude",
    "scheduler",
    "agents",
})

AGENT_PATCH_KEYS = frozenset({
    "name", "role", "type", "models", "provider", "max_concurrency", "launch",
})

AGENT_TYPE_META = {
    "hermes": {"label": "Hermes Agent", "note": "统一 Hermes 容器"},
    "hermes_profile": {"label": "Hermes Profile", "note": "Hermes --profile 多角色"},
    "openclaw": {"label": "OpenClaw Gateway", "note": "OpenClaw 本地 Gateway"},
    "cline": {"label": "Cline CLI", "note": "类 Claude Code 工作流 · 灵霄容器"},
    "opencode": {"label": "OpenCode CLI", "note": "OpenCode run · 大力容器"},
    "codex": {"label": "Codex CLI", "note": "codex exec · 灵霄/灵鉴 Docker"},
    "claude_code": {"label": "Claude Code CLI", "note": "宿主机 claude -p · Windows/Linux 可选"},
    "none": {"label": "纯文件", "note": "无 CLI 推送"},
}

# env 变量元数据（secret 仅显示是否已配置，PATCH 时传新值才更新）
ENV_SPECS: List[dict] = [
    {"key": "MAILBUS_OLLAMA_BASE_URL", "label": "Ollama 地址", "group": "llm", "placeholder": "http://127.0.0.1:11434"},
    {"key": "MAILBUS_OLLAMA_MODEL", "label": "Ollama 模型", "group": "llm", "placeholder": "qwen2.5:3b-instruct-q4_K_M"},
    {"key": "MAILBUS_INTERNAL_LLM_PROVIDER_PRIORITY", "label": "Provider 优先级", "group": "llm", "placeholder": "local,remote"},
    {"key": "MAILBUS_INTERNAL_LLM_API_KEY", "label": "Remote LLM API Key", "group": "llm", "secret": True},
    {"key": "DEEPSEEK_API_KEY", "label": "DeepSeek API Key", "group": "llm", "secret": True},
    {"key": "OPENAI_API_KEY", "label": "OpenAI API Key", "group": "llm", "secret": True},
    {"key": "N8N_PUBLISH_WEBHOOK_URL", "label": "n8n 发布 Webhook", "group": "n8n", "placeholder": "http://127.0.0.1:5678/webhook/mailbus-multi-publish"},
    {"key": "N8N_PUBLISH_WEBHOOK_SECRET", "label": "n8n Webhook Secret", "group": "n8n", "secret": True},
    {"key": "N8N_BASE_URL", "label": "n8n Base URL", "group": "n8n", "placeholder": "http://127.0.0.1:5678"},
    {"key": "COMFYUI_BASE_URL", "label": "ComfyUI 地址", "group": "comfyui", "placeholder": "http://127.0.0.1:8188"},
    {"key": "COMFYUI_CHECKPOINT", "label": "ComfyUI Checkpoint", "group": "comfyui"},
    {"key": "IMAGE_GENERATE_WEBHOOK_URL", "label": "生图 Webhook（可选）", "group": "n8n"},
    {"key": "CLINE_PROVIDER", "label": "Cline Provider（灵霄）", "group": "agents", "file": "store"},
    {"key": "CLINE_MODEL", "label": "Cline Model（灵霄）", "group": "agents", "file": "store"},
    {"key": "MAILBUS_API_TOKEN", "label": "Mailbus API Token", "group": "security", "secret": True},
]

SECTION_LABELS = {
    "mailbus_internal_llm": "Internal LLM / Planner",
    "mailbus_workflow": "Workflow & tool_live",
    "mailbus_automation": "自动化边界",
    "mailbus_intake_bridge": "Intake Bridge",
    "mailbus_codex": "Codex / Desktop 启动",
    "mailbus_claude": "Claude Code / Desktop 启动",
    "scheduler": "Scheduler 定时任务",
    "agents": "Agent 运行时",
}


def mailbus_root(data_dir: str) -> str:
    return os.path.dirname(os.path.normpath(data_dir))


def config_path(data_dir: str) -> str:
    return os.path.join(data_dir, "config.json")


def _env_paths(data_dir: str) -> List[str]:
    root = mailbus_root(data_dir)
    paths = [
        os.path.join(root, ".env"),
        os.path.join(root, "docker-agents", ".env"),
        os.path.join(data_dir, ".env"),
    ]
    out: List[str] = []
    seen: set[str] = set()
    for p in paths:
        ap = os.path.normpath(p)
        if ap not in seen:
            seen.add(ap)
            out.append(ap)
    return out


def _deep_merge(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _redact_api_token(config: dict) -> dict:
    out = copy.deepcopy(config)
    if out.get("api_token"):
        out["api_token"] = "***"
    return out


def list_sections() -> List[dict]:
    return [
        {"id": sid, "label": SECTION_LABELS.get(sid, sid), "editable": True}
        for sid in sorted(EDITABLE_SECTIONS)
    ]


def get_section(data_dir: str, section: str) -> dict:
    if section not in EDITABLE_SECTIONS:
        raise ValueError(f"unknown section: {section}")
    cfg = json_read(config_path(data_dir), {})
    if section == "agents":
        agents = cfg.get("agents") or {}
        types = cfg.get("agent_types") or {}
        model_tiers = list((types.get("models") or {}).keys())
        items = []
        for aid, ac in agents.items():
            meta = AGENT_TYPE_META.get(ac.get("type", ""), {})
            items.append({
                "id": aid,
                "name": ac.get("name", aid),
                "role": ac.get("role", ""),
                "type": ac.get("type"),
                "type_label": meta.get("label", ac.get("type")),
                "type_note": meta.get("note", ""),
                "models": ac.get("models") or [],
                "provider": ac.get("provider", ""),
                "max_concurrency": ac.get("max_concurrency", 1),
                "launch": ac.get("launch") or {},
                "has_browser": (ac.get("launch") or {}).get("has_browser"),
                "has_desktop": _agent_has_desktop_flag(ac, types),
            })
        return {
            "section": "agents",
            "agents": items,
            "model_tiers": model_tiers,
            "agent_types": {k: v for k, v in AGENT_TYPE_META.items()},
            "runtime_notes": {
                "claude_code": "已注册 · 宿主机 Claude CLI（mailbus_claude 平台配置）",
                "codex": "已注册 · Docker codex exec · skills 可挂载 .codex/skills",
                "dispatch_tier": (
                    "开发工程师派发：pro→灵云、flash→大力/灵霄（least_load+RR）；"
                    "详见 rules/model-routing.md · constraints.dispatch"
                ),
            },
        }
    if section == "scheduler":
        sched = cfg.get("scheduler") or {}
        return {
            "section": "scheduler",
            "data": {
                "enabled": sched.get("enabled", True),
                "tick_seconds": sched.get("tick_seconds", 10),
                "jobs": sched.get("jobs") or [],
            },
        }
    if section == "mailbus_intake_bridge":
        return {"section": section, "data": cfg.get(section) or {}}
    if section == "mailbus_codex":
        return {"section": section, "data": cfg.get("mailbus_codex") or {}}
    if section == "mailbus_claude":
        return {"section": section, "data": cfg.get("mailbus_claude") or {}}
    data = cfg.get(section) or {}
    if section == "mailbus_internal_llm":
        data = _sanitize_llm_section(copy.deepcopy(data))
    return {"section": section, "data": data}


def _sanitize_llm_section(data: dict) -> dict:
    for name, pc in (data.get("providers") or {}).items():
        if isinstance(pc, dict) and pc.get("api_key"):
            pc["api_key"] = "***"
    return data


def patch_section(data_dir: str, section: str, patch: dict) -> Tuple[dict, List[str]]:
    if section not in EDITABLE_SECTIONS:
        raise ValueError(f"unknown section: {section}")
    if not isinstance(patch, dict):
        raise ValueError("patch must be object")

    path = config_path(data_dir)
    cfg = json_read(path, {})
    requires_restart: List[str] = []

    if section == "agents":
        if "agent_id" not in patch or "fields" not in patch:
            raise ValueError("agents patch requires agent_id and fields")
        aid = patch["agent_id"]
        fields = patch["fields"]
        if aid not in (cfg.get("agents") or {}):
            raise ValueError(f"unknown agent: {aid}")
        ac = cfg["agents"][aid]
        for k, v in fields.items():
            if k not in AGENT_PATCH_KEYS:
                continue
            ac[k] = v
        requires_restart.append("agents")
    else:
        current = cfg.get(section) or {}
        if section == "mailbus_internal_llm":
            patch = _strip_llm_secrets_from_patch(patch)
        cfg[section] = _deep_merge(current, patch)
        if section in ("scheduler", "mailbus_internal_llm", "mailbus_intake_bridge"):
            requires_restart.append(section)

    errors = validate_config(cfg)
    blocking = [e for e in errors if e.startswith("agents.") and "未知字段" in e]
    if blocking:
        raise ValueError("; ".join(blocking[:3]))

    save_config(path, cfg)
    return {"section": section, "requires_restart": requires_restart, "warnings": errors[:5]}, requires_restart


def _strip_llm_secrets_from_patch(patch: dict) -> dict:
    p = copy.deepcopy(patch)
    for name, pc in (p.get("providers") or {}).items():
        if isinstance(pc, dict):
            if pc.get("api_key") in ("***", "", None):
                pc.pop("api_key", None)
    return p


def env_status(data_dir: str) -> dict:
    load_mailbus_env()
    groups: Dict[str, list] = {}
    for spec in ENV_SPECS:
        key = spec["key"]
        val = os.environ.get(key, "")
        configured = bool(val)
        entry = {
            "key": key,
            "label": spec["label"],
            "group": spec["group"],
            "secret": bool(spec.get("secret")),
            "configured": configured,
            "value": None if spec.get("secret") else (val or ""),
            "placeholder": spec.get("placeholder", ""),
            "file_hint": spec.get("file") or "project .env",
        }
        groups.setdefault(spec["group"], []).append(entry)
    return {"groups": groups, "specs": ENV_SPECS}


def patch_env(data_dir: str, vars_patch: dict) -> dict:
    allowed = {s["key"]: s for s in ENV_SPECS}
    root = mailbus_root(data_dir)
    primary = os.path.join(root, ".env")
    if not os.path.isfile(primary):
        example = os.path.join(root, "docker-agents", ".env.example")
        if os.path.isfile(example):
            import shutil
            shutil.copy(example, primary)
        else:
            os.makedirs(os.path.dirname(primary) or root, exist_ok=True)
            open(primary, "a", encoding="utf-8").close()

    updated: List[str] = []
    skipped: List[str] = []
    for key, val in (vars_patch or {}).items():
        if key not in allowed:
            skipped.append(key)
            continue
        if val is None or val == "" or val == "***":
            continue
        spec = allowed[key]
        target = primary
        if spec.get("file") == "store":
            target = os.path.join(data_dir, ".env")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if not os.path.isfile(target):
                open(target, "a", encoding="utf-8").close()
        _set_env_key(target, key, str(val))
        updated.append(key)

    load_mailbus_env()
    return {"updated": updated, "skipped": skipped, "requires_restart": ["env"]}


def _set_env_key(path: str, key: str, value: str) -> None:
    lines: List[str] = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    pat = re.compile(rf"^\s*{re.escape(key)}=")
    found = False
    out: List[str] = []
    for line in lines:
        if pat.match(line):
            found = True
            out.append(f"{key}={value}\n")
        else:
            out.append(line)
    if not found:
        if out and not out[-1].endswith("\n"):
            out[-1] = out[-1] + "\n"
        out.append(f"{key}={value}\n")
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(out)
