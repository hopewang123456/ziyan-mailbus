"""Mailbus 配置中心 — UI 读写 config.json 与 .env（脱敏）。"""

from __future__ import annotations

import copy
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from lib.application.commands.commands import save_config
from .config_schema import validate_config
from lib.infra.env_bootstrap import load_mailbus_env
from lib.adapters.integrations.model_router import TIER_OLLAMA
from lib.infra.utils import json_read, json_write


def _agent_has_desktop_flag(agent_cfg: dict, agent_types: dict) -> bool:
    from lib.adapters.frameworks.desktop_launch import agent_has_desktop

    return agent_has_desktop(agent_cfg, agent_types)


def _agent_auth_summary(agent_cfg: dict, agent_id: str, data_dir: str = "") -> dict:
    """agent 浏览器鉴权摘要（只读，不触发自动生成）。"""
    auth_block = (agent_cfg or {}).get("auth") or {}
    mode = (auth_block.get("mode") or "none").strip().lower()
    generated = False
    try:
        from lib.adapters.config import token_store

        refs = [
            agent_id,
            str(auth_block.get("token_ref") or "").strip(),
            str(auth_block.get("password_ref") or "").strip(),
            str(auth_block.get("username_ref") or "").strip(),
        ]
        for ref in refs:
            if not ref:
                continue
            cred = token_store.browser_credentials(data_dir, ref)
            if cred.get("token") or cred.get("password"):
                generated = True
                break
    except Exception:
        pass
    return {
        "mode": mode if auth_block else ("auto" if generated else "none"),
        "authed": mode in ("token", "basic") or generated,
        "configured": bool(auth_block) or generated,
        "generated": generated,
    }


def _enrich_agent_instances(instances: dict, data_dir: str) -> dict:
    """Attach auth summary + requires flag for config UI instance cards."""
    from lib.adapters.config.auth_policy import agent_requires_browser_auth
    from lib.adapters.frameworks.framework_discovery import (
        framework_default_install_path,
        framework_run_targets,
    )

    out: dict = {}
    for iid, inst in (instances or {}).items():
        if not isinstance(inst, dict):
            continue
        e = dict(inst)
        atype = (e.get("type") or "").strip()
        # 实例级监测开关默认开；distro 仅 wsl/linux 有意义
        e.setdefault("enabled", True)
        e.setdefault("distro", "auto")
        e["auth_summary"] = _agent_auth_summary(e, str(e.get("id") or iid), data_dir)
        e["auth_required"] = agent_requires_browser_auth(atype, e)
        e["install_path_default"] = framework_default_install_path(atype)
        e["run_targets"] = framework_run_targets(atype)
        out[str(e.get("id") or iid)] = e
    return out

# 可在 Dashboard 编辑的 config.json 段
EDITABLE_SECTIONS = frozenset({
    "mailbus_internal_llm",
    "mailbus_workflow",
    "mailbus_automation",
    "mailbus_intake_bridge",
    "mailbus_codex",
    "mailbus_claude",
    "mailbus_chains",
    "scheduler",
    "agents",
    "frameworks",
    "launch_ports",
    "smart_routing",
    "services",
    "harness",
    "asset_paths",
    "browser_hosts",
})

AGENT_PATCH_KEYS = frozenset({
    "name", "role", "type", "models", "provider", "max_concurrency", "launch",
    "enabled", "native_config_path", "native_config", "archetype", "framework",
    "auth", "paths",
    "skill_groups", "persona_files",
})

AGENT_TYPE_META = {
    "hermes": {"label": "Hermes Agent", "note": "统一 Hermes 容器"},
    "hermes_profile": {"label": "Hermes Profile", "note": "Hermes --profile 多角色"},
    "openclaw": {"label": "OpenClaw Gateway", "note": "OpenClaw 本地 Gateway"},
    "cline": {"label": "Cline CLI", "note": "类 Claude Code 工作流 · codex 容器"},
    "opencode": {"label": "OpenCode CLI", "note": "OpenCode run · opencode 容器"},
    "codex": {"label": "Codex CLI", "note": "codex exec · codex Docker"},
    "claude_code": {"label": "Claude Code CLI", "note": "宿主机 claude -p · Windows/Linux 可选"},
    "cursor": {"label": "Cursor", "note": "Windows Cursor IDE / cursor-agent CLI"},
    "none": {"label": "纯文件", "note": "无 CLI 推送"},
}


def _skillgroup_root() -> str:
    from .assemble import skillgroup_root

    return str(skillgroup_root())


def _skillgroup_groups() -> list[str]:
    from .assemble import list_skill_groups

    return list_skill_groups()

# env 变量元数据（secret 仅显示是否已配置，PATCH 时传新值才更新）
ENV_SPECS: List[dict] = [
    {
        "key": "MAILBUS_OLLAMA_BASE_URL",
        "label": "Ollama 地址（宿主覆盖；Docker 以 services.docker 为准）",
        "group": "llm",
        "placeholder": "http://127.0.0.1:11434",
    },
    {"key": "MAILBUS_OLLAMA_MODEL", "label": "Ollama 模型", "group": "llm", "placeholder": "qwen2.5:3b-instruct-q4_K_M"},
    {
        "key": "AGENTMEMORY_URL",
        "label": "AgentMemory 地址（宿主覆盖；Docker 以 services.docker 为准）",
        "group": "llm",
        "placeholder": "http://127.0.0.1:3111",
    },
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
    {"key": "CLINE_PROVIDER", "label": "Cline Provider", "group": "agents", "file": "store"},
    {"key": "CLINE_MODEL", "label": "Cline Model", "group": "agents", "file": "store"},
    {"key": "MAILBUS_API_TOKEN", "label": "Mailbus API Token", "group": "security", "secret": True},
    {"key": "OPENCLAW_GATEWAY_TOKEN", "label": "OpenClaw Gateway Token", "group": "gateway", "secret": True},
    {
        "key": "MAILBUS_SKILLS_ROOT",
        "label": "技能根（默认=仓库 skills/ junction→Vault；自定义=Obsidian 012-skills）",
        "group": "asset_paths",
        "placeholder": "E:\\Obsidian\\Vaults\\Agent\\01-mailbus\\012-skills",
    },
    {
        "key": "MAILBUS_RULES_ROOT",
        "label": "规则根（默认=仓库 rules/ junction→Vault；自定义=Obsidian 011-rule）",
        "group": "asset_paths",
        "placeholder": "E:\\Obsidian\\Vaults\\Agent\\01-mailbus\\011-rule",
    },
    {
        "key": "MAILBUS_IDENTITIES_ROOT",
        "label": "身份根（默认=仓库 identities/ junction→Vault；自定义=Obsidian 018-identities）",
        "group": "asset_paths",
        "placeholder": "E:\\Obsidian\\Vaults\\Agent\\01-mailbus\\018-identities",
    },
    {
        "key": "AGENT_VAULT_ROOT",
        "label": "Agent Vault 根（人物/技能/身份 SoT；默认自动推断）",
        "group": "paths",
        "placeholder": "E:\\Obsidian\\Vaults\\Agent",
    },
    {
        "key": "MEMORY_BRIDGE_AGENTMEMORY",
        "label": "AgentMemory 桥接（0=SQLite-only 降级，1=完整 AgentMemory）",
        "group": "memory",
        "placeholder": "1",
    },
]

SECTION_LABELS = {
    "mailbus_internal_llm": "Internal LLM / Planner",
    "mailbus_workflow": "Workflow & tool_live",
    "mailbus_automation": "自动化边界",
    "mailbus_intake_bridge": "Intake Bridge",
    "mailbus_codex": "Codex / Desktop 启动",
    "mailbus_claude": "Claude Code / Desktop 启动",
    "mailbus_chains": "工单链路模板 / 日预算",
    "scheduler": "Scheduler 定时任务",
    "agents": "Agent 运行时",
    "frameworks": "Framework enable / 路径",
    "launch_ports": "Launch 端口",
    "smart_routing": "智能路由 / L0–L3",
    "services": "外部服务 / 接线",
    "asset_paths": "资产路径（skill/rule/identity · 默认/自定义）",
    "harness": "Harness / 规则路径",
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
        from lib.adapters.config.agent_instances import (
            _instances_fragmented_by_port,
            _roles_split_across_instances,
            synthesize_instances_from_agents,
        )
        from lib.adapters.frameworks.framework_discovery import (
            framework_default_install_path,
            framework_run_targets,
        )

        prev_instances = cfg.get("agent_instances") if isinstance(cfg.get("agent_instances"), dict) else {}
        need_persist = (
            (not prev_instances)
            or _instances_fragmented_by_port(prev_instances)
            or _roles_split_across_instances(cfg.get("agents") or {}, prev_instances)
        )
        cfg = synthesize_instances_from_agents(cfg)
        if need_persist:
            try:
                from lib.infra.utils import json_write

                json_write(config_path(data_dir), cfg)
            except OSError:
                pass

        agents = cfg.get("agents") or {}
        types = cfg.get("agent_types") or {}
        model_tiers = list((types.get("models") or {}).keys())
        instances = cfg.get("agent_instances") or {}
        items = []
        for aid, ac in agents.items():
            meta = AGENT_TYPE_META.get(ac.get("type", ""), {})
            fw = ac.get("type") or ""
            # 运行环境字段唯一 SoT 在实例；角色只读继承（角色卡无编辑入口）
            iid = ac.get("instance_id") or ""
            inst = instances.get(iid) if isinstance(instances.get(iid), dict) else {}
            inherited_install = (inst.get("install_path") or "").strip()
            inherited_run = (inst.get("run_target") or "windows").strip()
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
                "enabled": ac.get("enabled"),
                "native_config_path": ac.get("native_config_path") or (ac.get("native_config") or {}).get("path"),
                "install_path": inherited_install,
                "install_path_default": framework_default_install_path(fw),
                "install_configured": bool(inherited_install),
                "run_target": inherited_run,
                "run_targets": framework_run_targets(fw),
                "has_browser": (ac.get("launch") or {}).get("has_browser"),
                "has_desktop": _agent_has_desktop_flag(ac, types),
                "auth": _agent_auth_summary(ac, aid, data_dir),
                "instance_id": iid,
                "instance_enabled": inst.get("enabled", True),
                "host": inst.get("host") or "",
                "port": ac.get("port") if ac.get("port") not in (None, "") else inst.get("port"),
                "custom_paths": bool(inst.get("custom_paths")),
                "distro": inst.get("distro") or "auto",
                "paths": ac.get("paths") if isinstance(ac.get("paths"), dict) else {},
                "skill_groups": ac.get("skill_groups") if isinstance(ac.get("skill_groups"), list) else [],
                "persona_files": ac.get("persona_files") if isinstance(ac.get("persona_files"), list) else [],
            })
        return {
            "section": "agents",
            "agents": items,
            "agent_instances": _enrich_agent_instances(
                cfg.get("agent_instances") or {}, data_dir
            ),
            "model_tiers": model_tiers,
            "agent_types": {k: v for k, v in AGENT_TYPE_META.items()},
            "skillgroup": {
                "root": str(_skillgroup_root()),
                "groups": _skillgroup_groups(),
                "note": "一级子目录=组；角色卡可多选（agents.<id>.skill_groups[]）；同名覆盖 私有>组>框架",
            },
            "runtime_notes": {
                "claude_code": "已注册 · 宿主机 Claude CLI（mailbus_claude 平台配置）",
                "codex": "已注册 · Docker codex exec · skills 可挂载 .codex/skills",
                "dispatch_tier": (
                    "开发工程师派发：pro→高能力模型 agent、flash→快速 agent（least_load+RR）；"
                    "详见 rules/model-routing.md · constraints.dispatch"
                ),
                "dual_layer": (
                    "配置页：Agent 实例卡 → 加载角色；花名册为角色卡（instance_id 归属）。"
                    "见 Vault 0173-plans/cross-env-three-end-auth-clarify.md"
                ),
            },
        }
    if section == "launch_ports":
        from .launch_ports import collect_launch_port_items, load_launch_port_defaults

        agents = cfg.get("agents") or {}
        types = cfg.get("agent_types") or {}
        return {
            "section": "launch_ports",
            "agents": collect_launch_port_items(agents, types),
            "defaults": load_launch_port_defaults(),
            "notes": {
                "priority": "launch.browser 自定义 > docker.port > config/mailbus/launch-ports.json 默认",
                "claude_sync": "Claude agent 保存时同步 mailbus_claude.platforms.*.browser_ports",
            },
        }
    if section == "smart_routing":
        from lib.adapters.orchestration.complexity_router import (
            DEFAULT_TIER_MAP_CLOUD,
            DEFAULT_TIER_MAP_OLLAMA,
            load_smart_routing_config,
        )
        from lib.adapters.integrations.ollama_routing import is_ollama_ready, resolve_ollama_settings

        sr = load_smart_routing_config(cfg)
        types = cfg.get("agent_types") or {}
        model_aliases = list((types.get("models") or {}).keys())
        if TIER_OLLAMA not in model_aliases:
            model_aliases = list(model_aliases) + ["ollama-local"]
        ollama_settings = resolve_ollama_settings(cfg, data_dir)
        return {
            "section": "smart_routing",
            "data": sr,
            "ollama": {
                "ready": is_ollama_ready(cfg, data_dir=data_dir),
                "base_url": ollama_settings["base_url"],
                "model": ollama_settings["model"],
            },
            "model_aliases": sorted(set(model_aliases)),
            "tier_options": ["L0", "L1", "L2", "L3"],
            "defaults": {
                "ollama_online": dict(DEFAULT_TIER_MAP_OLLAMA),
                "ollama_offline": dict(DEFAULT_TIER_MAP_CLOUD),
            },
            "notes": {
                "tier2": "推送阶段 Tier-2：L0–L2 常规走本机 Ollama（在线时），L3 可走云端 Pro",
                "pro_gate": "deepseek-pro 仍须环境变量 MAILBUS_ALLOW_PRO=1",
                "gpu": "与 ComfyUI 分时见 gpu_sharing（Internal LLM 段）",
                "services_tab": "URL/模型接线请到「外部服务」段编辑，本段只管 L0–L3→alias",
            },
        }
    if section == "services":
        return _get_services_section(cfg, data_dir)
    if section == "asset_paths":
        return _get_asset_paths_section(cfg, data_dir)
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


def _get_services_section(cfg: dict, data_dir: str) -> dict:
    from lib.adapters.ops.service_registry import (
        compose_env_for_services,
        detect_runtime,
        probe_service,
        service_settings,
    )

    runtime = detect_runtime()
    ollama = service_settings("ollama", config=cfg, data_dir=data_dir)
    am = service_settings("agentmemory", config=cfg, data_dir=data_dir)
    ollama_probe = probe_service("ollama", config=cfg, data_dir=data_dir)
    am_probe = probe_service("agentmemory", config=cfg, data_dir=data_dir)
    store_svc = copy.deepcopy(cfg.get("services") or {})
    # Ensure editable profile shells exist for UI
    for name, settings in (("ollama", ollama), ("agentmemory", am)):
        block = store_svc.setdefault(name, {})
        if not isinstance(block.get("profiles"), dict) or not block["profiles"]:
            block["profiles"] = copy.deepcopy(settings.get("profiles") or {})
        if name == "ollama" and not block.get("model"):
            block["model"] = settings.get("model") or ""
        if name == "agentmemory" and not block.get("health_path"):
            block["health_path"] = settings.get("health_path") or "/agentmemory/health"
    return {
        "section": "services",
        "runtime": runtime,
        "data": store_svc,
        "compose_env": compose_env_for_services(config=cfg, data_dir=data_dir),
        "ollama": {
            "ready": bool(ollama_probe.get("ok")),
            "effective_url": ollama.get("base_url"),
            "model": ollama.get("model"),
            "proxy": ollama.get("proxy") or {},
            "profiles": ollama.get("profiles") or {},
            "probe": ollama_probe,
        },
        "agentmemory": {
            "ready": bool(am_probe.get("ok")),
            "effective_url": am.get("base_url"),
            "health_path": am.get("health_path"),
            "profiles": am.get("profiles") or {},
            "probe": am_probe,
        },
        "notes": {
            "profiles": "windows / wsl / docker 三套 base_url；改 docker URL 后需 compose sync + start-team",
            "smart_routing": "L0–L3→alias 在「智能路由」段；本段只管服务在哪",
            "env": "宿主 .env 可覆盖本机 URL，不会写入 Docker profile",
        },
    }


# 资产路径段（28b）：skill/rule/identity 三项，默认=仓库内 junction 路径，自定义=Obsidian Vault 目录
ASSET_PATH_SPECS = [
    {
        "key": "skills",
        "env": "MAILBUS_SKILLS_ROOT",
        "default": "skills",
        "vault": "Agent/01-mailbus/012-skills",
        "label": "技能",
        "hint": "默认=仓库 skills/（junction→Vault）；自定义=Obsidian 01-mailbus/012-skills",
    },
    {
        "key": "rules",
        "env": "MAILBUS_RULES_ROOT",
        "default": "rules",
        "vault": "Agent/01-mailbus/011-rule",
        "label": "规则",
        "hint": "默认=仓库 rules/（junction→Vault）；自定义=Obsidian 01-mailbus/011-rule",
    },
    {
        "key": "identity",
        "env": "MAILBUS_IDENTITIES_ROOT",
        "default": "identities",
        "vault": "Agent/01-mailbus/018-identities",
        "label": "身份",
        "hint": "默认=仓库 identities/（junction→Vault）；自定义=Obsidian 01-mailbus/018-identities",
    },
]


def _get_asset_paths_section(cfg: dict, data_dir: str) -> dict:
    """skill/rule/identity 三资产当前生效路径 + env 覆盖状态（只读）。"""
    from lib.infra.constants import (
        MAILBUS_IDENTITIES_ROOT,
        MAILBUS_RULES_ROOT,
        MAILBUS_SKILLS_ROOT,
        PROJECT_ROOT,
    )

    load_mailbus_env()
    root = PROJECT_ROOT
    defaults = {
        "skills": str(MAILBUS_SKILLS_ROOT),
        "rules": str(MAILBUS_RULES_ROOT),
        "identity": str(MAILBUS_IDENTITIES_ROOT),
    }
    items = []
    for spec in ASSET_PATH_SPECS:
        env_val = os.environ.get(spec["env"], "").strip()
        effective = env_val or defaults[spec["key"]]
        mode = "custom" if env_val else "default"
        items.append({
            "key": spec["key"],
            "label": spec["label"],
            "env": spec["env"],
            "default": str(root / spec["default"]),
            "effective": effective,
            "mode": mode,
            "custom": env_val,
            "vault": spec["vault"],
            "hint": spec["hint"],
            "exists": os.path.isdir(effective),
        })
    return {
        "section": "asset_paths",
        "data": {"items": items},
        "note": "两态原则：项目内只允许冻结最小版（默认）或 example；自定义指向 Obsidian Vault 时避免双源。保存即写 .env（patch_env）。",
    }


def _persist_services_seed(data_dir: str, services: dict) -> List[str]:
    """Write ollama/agentmemory blocks back to config/services/*.json seeds."""
    root = mailbus_root(data_dir)
    seed_dir = os.path.join(root, "config", "services")
    os.makedirs(seed_dir, exist_ok=True)
    written: List[str] = []
    for name in ("ollama", "agentmemory"):
        block = services.get(name)
        if not isinstance(block, dict):
            continue
        path = os.path.join(seed_dir, f"{name}.json")
        existing = json_read(path, {}) if os.path.isfile(path) else {}
        merged = _deep_merge(existing if isinstance(existing, dict) else {}, block)
        merged.setdefault("id", name)
        json_write(path, merged)
        written.append(path)
    try:
        from lib.adapters.ops.service_registry import clear_service_registry_cache

        clear_service_registry_cache()
    except Exception:
        pass
    return written


def patch_section(data_dir: str, section: str, patch: dict) -> Tuple[dict, List[str]]:
    if section not in EDITABLE_SECTIONS:
        raise ValueError(f"unknown section: {section}")
    if not isinstance(patch, dict):
        raise ValueError("patch must be object")

    path = config_path(data_dir)
    cfg = json_read(path, {})
    requires_restart: List[str] = []
    persist_seed = bool(patch.pop("persist_seed", False)) if section == "services" else False

    if section == "agents":
        if "agent_id" not in patch or "fields" not in patch:
            raise ValueError("agents patch requires agent_id and fields")
        aid = patch["agent_id"]
        fields = patch["fields"]
        if aid not in (cfg.get("agents") or {}):
            raise ValueError(f"unknown agent: {aid}")
        ac = cfg["agents"][aid]
        # 角色级 patch 只允许角色字段（运行环境字段走实例接口 /api/agent-instances）
        for k, v in fields.items():
            if k not in AGENT_PATCH_KEYS:
                continue
            if k == "endpoint" and isinstance(v, dict):
                ac["endpoint"] = v
                continue
            ac[k] = v
        requires_restart.append("agents")
        # A2A 可用性：保存时探测 endpoint 并写回 channels.a2a.available（运行时只认配置）
        from lib.adapters.transport.a2a_probe import stamp_a2a_probe

        stamp_a2a_probe(ac)
        # 必填凭证：保存后若仍无凭据 → 返回网页端获取 URL（不阻断其它字段落盘）
        from lib.adapters.config.auth_policy import (
            agent_has_stored_browser_cred,
            agent_requires_browser_auth,
            raw_browser_entry_url,
        )

        atype = (ac.get("type") or "").strip()
        auth_gate: dict = {}
        if agent_requires_browser_auth(atype, ac) and not agent_has_stored_browser_cred(data_dir, aid, ac):
            auth_gate = {
                "auth_required": True,
                "obtain_credential_url": raw_browser_entry_url(data_dir, aid, ac),
                "auth_hint": "该 Agent 类型需要登录凭证；已保存其它字段，请在打开的网页端完成登录/取凭据后写回卡片",
            }
        # 人设 V1：保存用户添加的人设文件时校验路径存在（不探活），缺失仅警告、仍落盘
        persona_warn: dict = {}
        if "persona_files" in fields:
            from .assemble import verify_persona_files

            pf = ac.get("persona_files") if isinstance(ac.get("persona_files"), list) else []
            missing = verify_persona_files([str(x) for x in pf])
            if missing:
                persona_warn = {
                    "persona_warning": "部分人设在 Agent 中不存在，可能无法正常沟通",
                    "persona_missing": missing,
                }
        json_write(path, cfg)
        return {"section": "agents", "agent_id": aid, "agent": ac, **auth_gate, **persona_warn}, requires_restart
    elif section == "launch_ports":
        updates = patch.get("updates")
        if updates is None and patch.get("agent_id"):
            updates = [patch]
        if not isinstance(updates, list) or not updates:
            raise ValueError("launch_ports patch requires updates[] or agent_id")
        for item in updates:
            if not isinstance(item, dict) or not item.get("agent_id"):
                raise ValueError("each update requires agent_id")
            from .launch_ports import apply_launch_port_patch

            apply_launch_port_patch(
                cfg,
                str(item["agent_id"]),
                port=int(item["port"]) if item.get("port") not in (None, "") else None,
                ttyd_port=int(item["ttyd_port"]) if item.get("ttyd_port") not in (None, "") else None,
                reset=bool(item.get("reset")),
            )
        requires_restart.append("launch_ports")
    elif section == "services":
        # Accept either {ollama:..., agentmemory:...} or {data: {...}} or nested under services
        body = patch.get("data") if isinstance(patch.get("data"), dict) else patch
        if isinstance(body.get("services"), dict):
            body = body["services"]
        current = cfg.get("services") or {}
        cfg["services"] = _deep_merge(current, body)
        requires_restart.append("services")
        if persist_seed:
            _persist_services_seed(data_dir, cfg["services"])
        try:
            from lib.adapters.ops.service_registry import clear_service_registry_cache
            from lib.adapters.integrations.ollama_routing import invalidate_ollama_probe_cache

            clear_service_registry_cache()
            invalidate_ollama_probe_cache()
        except Exception:
            pass
    elif section == "browser_hosts":
        # 浏览器白名单（IP/CIDR 数组）；也可 MAILBUS_BROWSER_HOSTS env 覆盖、直接编辑 config.json
        hosts = patch.get("browser_hosts") if isinstance(patch.get("browser_hosts"), list) else None
        if hosts is None and isinstance(patch, list):
            hosts = patch
        if hosts is not None:
            cfg["browser_hosts"] = [str(h).strip() for h in hosts if str(h).strip()]
        requires_restart.append("browser_hosts")
    elif section == "asset_paths":
        # 资产路径：自定义 → 写对应 env；默认 → 删除 env 键（回落到仓库 junction 默认）
        allowed_env = {s["env"] for s in ASSET_PATH_SPECS}
        items = patch.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("asset_paths patch requires items[]")
        root = mailbus_root(data_dir)
        env_path = os.path.join(root, ".env")
        updated: List[str] = []
        pending: List[Tuple[str, str | None]] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            env_key = it.get("env") or ""
            if env_key not in allowed_env:
                continue
            mode = it.get("mode", "default")
            if mode == "custom" and it.get("custom"):
                pending.append((env_key, str(it["custom"])))
            elif mode == "default":
                pending.append((env_key, None))
        if pending and not os.path.isfile(env_path):
            os.makedirs(root, exist_ok=True)
            open(env_path, "a", encoding="utf-8").close()
        for env_key, val in pending:
            if val is None:
                _unset_env_key(env_path, env_key)
            else:
                _set_env_key(env_path, env_key, val)
            updated.append(env_key)
        load_mailbus_env()
        return {
            "section": "asset_paths",
            "requires_restart": ["env"],
            "warnings": [],
            "updated": updated,
        }, ["env"]
    else:
        current = cfg.get(section) or {}
        if section == "mailbus_internal_llm":
            patch = _strip_llm_secrets_from_patch(patch)
        cfg[section] = _deep_merge(current, patch)
        if section in ("scheduler", "mailbus_internal_llm", "mailbus_intake_bridge", "smart_routing"):
            requires_restart.append(section)
        if section == "smart_routing":
            from lib.adapters.integrations.ollama_routing import invalidate_ollama_probe_cache

            invalidate_ollama_probe_cache()

    errors = validate_config(cfg)
    blocking = [e for e in errors if e.startswith("agents.") and "未知字段" in e]
    if blocking:
        raise ValueError("; ".join(blocking[:3]))

    save_config(path, cfg)
    result: dict = {"section": section, "requires_restart": requires_restart, "warnings": errors[:5]}
    if section == "services":
        result.update(_get_services_section(cfg, data_dir))
        if persist_seed:
            result["persist_seed"] = True
    return result, requires_restart


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


def _unset_env_key(path: str, key: str) -> None:
    """删除 .env 中的键（回落到默认）。"""
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    pat = re.compile(rf"^\s*{re.escape(key)}=")
    out = [line for line in lines if not pat.match(line)]
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(out)
