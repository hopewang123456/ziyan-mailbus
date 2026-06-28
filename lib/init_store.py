"""init-store — aggregate mail/config + org/ + access/ → store/ runtime skeleton."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from .agent_registry import clear_agent_registry_cache, load_all_agents
from .sync_layers import mirror_rules_to_store
from .constants import (
    DEFAULT_ACK_TIMEOUT,
    DEFAULT_ARCHIVE_DAYS,
    DEFAULT_ARCHIVE_MAX_MESSAGES,
    DEFAULT_MAX_RETRIES,
    MAILBUS_ROOT,
    MAILBUS_VERSION,
    _now_iso,
)
from .utils import json_write

ORG_JSON_MIRROR = (
    "roster.json",
    "role-flow.json",
    "role-types.json",
    "capabilities.json",
    "role-responsibilities.json",
    "agent-registry.json",
)

RUNTIME_SUBDIRS = (
    "inbox",
    "leads",
    "queue/urgent",
    "queue/normal",
    "archive",
    "errors",
    "logs",
    "msg-files",
    "msg-results",
    "patches",
    "replies",
    "tasks",
    "work-orders",
    "deliverables",
    "locks",
    "agentmemory-pending",
    "roles/json",
    "rules",
    "workflows",
    "dispatch",
    "billing",
    "system",
)

ARCHETYPE_ROLE_ZH: dict[str, str] = {
    "spec-designer": "方案设计",
    "security-auditor": "网络安全",
    "tech-radar": "技术雷达",
    "market-expansion": "市场拓展",
    "code-reviewer": "代码审查",
    "test-engineer": "质量验证",
    "patroller": "运维巡检",
    "tech-lead": "技术负责人",
    "coding-executor": "编码执行",
    "coding-pro": "精细编码",
    "orchestrator": "调度协调",
    "operations": "内容运营",
    "finance-followup": "财务跟进",
}

DEFAULT_MODELS: dict[str, list[str]] = {
    "hermes_profile": ["deepseek-flash"],
    "codex": ["deepseek-flash"],
    "claude_code": ["minimax-m2"],
    "openclaw": ["deepseek-flash"],
    "opencode": ["deepseek-flash", "qwen-max", "zhipu-4"],
}


def mailbus_root(mail_root: Path | str | None = None) -> Path:
    return Path(mail_root) if mail_root is not None else MAILBUS_ROOT


def _deep_merge(dst: dict, src: dict) -> dict:
    for key, val in (src or {}).items():
        if key in dst and isinstance(dst[key], dict) and isinstance(val, dict):
            _deep_merge(dst[key], val)
        else:
            dst[key] = val
    return dst


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default


def load_roster(mail_root: Path | None = None) -> dict[str, Any]:
    path = mailbus_root(mail_root) / "org" / "json" / "roster.json"
    data = _read_json(path, {})
    members = {}
    for item in data.get("members") or []:
        if isinstance(item, dict) and item.get("id"):
            members[item["id"]] = item
    return members


def load_config_fragments(mail_root: Path | None = None) -> dict[str, Any]:
    """Merge mail/config/**/*.json into a store config fragment (no agents)."""
    root = mailbus_root(mail_root)
    cfg_dir = root / "config"
    merged: dict[str, Any] = {}

    base_path = cfg_dir / "mailbus" / "base.json"
    if base_path.is_file():
        _deep_merge(merged, _read_json(base_path, {}))

    llm_root = merged.setdefault("mailbus_internal_llm", {})
    ollama = cfg_dir / "llm" / "ollama.json"
    if ollama.is_file():
        llm_root["ollama"] = _read_json(ollama, {})
    routing = cfg_dir / "llm" / "routing.json"
    if routing.is_file():
        llm_root["routing"] = _read_json(routing, {})

    scheduler = cfg_dir / "scheduler" / "jobs.json"
    if scheduler.is_file():
        merged["scheduler"] = _read_json(scheduler, {})

    intake_bridge = cfg_dir / "intake" / "bridge.json"
    if intake_bridge.is_file():
        merged["mailbus_intake_bridge"] = _deep_merge(
            merged.get("mailbus_intake_bridge") or {},
            _read_json(intake_bridge, {}),
        )

    launch_watchdog = cfg_dir / "launch" / "watchdog.json"
    if launch_watchdog.is_file():
        merged["mailbus_launch_watchdog"] = _read_json(launch_watchdog, {})

    pipeline_ops = merged.setdefault("pipeline_ops", {})
    role_failover = cfg_dir / "pipeline" / "role_failover.json"
    if role_failover.is_file():
        rf_data = _read_json(role_failover, {})
        pipeline_ops["role_failover"] = rf_data
        pipeline_ops["max_failures_per_step"] = rf_data.get("max_failures_per_step", 2)
    dispatch_cfg = cfg_dir / "pipeline" / "dispatch.json"
    if dispatch_cfg.is_file():
        pipeline_ops["dispatch"] = _read_json(dispatch_cfg, {})
    verify_cfg = cfg_dir / "pipeline" / "verify.json"
    if verify_cfg.is_file():
        auto = merged.setdefault("mailbus_automation", {})
        auto["verify"] = _deep_merge(auto.get("verify") or {}, _read_json(verify_cfg, {}))
    decomp_cfg = cfg_dir / "pipeline" / "decomposition.json"
    if decomp_cfg.is_file():
        pipeline_ops["decomposition"] = _read_json(decomp_cfg, {})
    workflow = cfg_dir / "pipeline" / "workflow-routes.json"
    if workflow.is_file():
        merged["mailbus_workflow"] = _read_json(workflow, {})

    fd = merged.setdefault("framework_delivery", {})
    oc_delivery = cfg_dir / "frameworks" / "opencode" / "delivery.json"
    if oc_delivery.is_file():
        fd["opencode"] = _read_json(oc_delivery, {})

    agents_dir = cfg_dir / "agents"
    if agents_dir.is_dir():
        merged["_agent_overrides"] = {}
        for path in sorted(agents_dir.glob("*.json")):
            stem = path.stem
            if stem.endswith(".override"):
                agent_id = stem[: -len(".override")]
            else:
                agent_id = stem
            merged["_agent_overrides"][agent_id] = _read_json(path, {})

    return merged


def build_agent_entry(
    agent_id: str,
    agent_rec: dict[str, Any],
    roster_member: dict[str, Any] | None,
    *,
    data_dir: str,
    override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    framework = agent_rec.get("framework") or "none"
    archetype = agent_rec.get("archetype") or ""
    roster_member = roster_member or {}

    display = roster_member.get("display") or {}
    name = roster_member.get("name") or display.get("zh") or agent_id
    role = roster_member.get("role") or ARCHETYPE_ROLE_ZH.get(archetype, archetype or framework)

    entry: dict[str, Any] = {
        "name": name,
        "role": role,
        "type": framework,
        "agent_id": agent_id,
        "archetype": archetype,
        "max_concurrency": 1,
        "models": list(DEFAULT_MODELS.get(framework, ["deepseek-flash"])),
        "inbox": os.path.join(data_dir, "inbox", agent_id, "inbox.json").replace("\\", "/"),
    }

    docker = agent_rec.get("docker") or {}
    if framework == "hermes_profile":
        entry["profile"] = docker.get("profile") or agent_id
    if framework == "openclaw":
        entry["agent"] = agent_id

    if docker:
        entry["docker"] = dict(docker)

    workspace = agent_rec.get("workspace")
    if workspace:
        entry["push"] = {"cwd": workspace}
    elif framework == "codex":
        entry["push"] = {
            "cwd": "/mailbus/store",
            "sandbox": "danger-full-access",
            "pipeline_sandbox": "danger-full-access",
            "pipeline_model": "deepseek-flash",
        }

    for block in ("launch", "profile_paths"):
        if agent_rec.get(block):
            entry[block] = dict(agent_rec[block]) if isinstance(agent_rec[block], dict) else agent_rec[block]

    if framework == "claude_code" and "launch" not in entry:
        entry["launch"] = {
            "template": "claude_host",
            "launch_via_api": True,
            "has_browser": True,
        }
    if framework in ("codex",) and "launch" not in entry:
        entry["launch"] = {
            "template": "codex_docker",
            "launch_via_api": True,
            "has_browser": True,
        }
    if framework == "hermes_profile" and "launch" not in entry:
        port = docker.get("port")
        entry["launch"] = {
            "template": "hermes_dashboard",
            "has_browser": bool(port),
        }
    if framework == "openclaw" and "launch" not in entry:
        entry["launch"] = {
            "template": "openclaw_gateway",
            "launch_via_api": True,
            "has_browser": True,
        }
    if "profile_paths" not in entry:
        identity = f"mail/skills/roles/overlays/{agent_id}/SKILL.md"
        entry["profile_paths"] = {"identity": identity}

    if override:
        _deep_merge(entry, override)
    return entry


def build_agents_from_registry(
    *,
    data_dir: str,
    mail_root: Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    clear_agent_registry_cache()
    registry = load_all_agents(mail_root=mail_root, refresh=True)
    roster = load_roster(mail_root)
    overrides = overrides or {}
    agents: dict[str, dict[str, Any]] = {}
    for agent_id in sorted(registry):
        agents[agent_id] = build_agent_entry(
            agent_id,
            registry[agent_id],
            roster.get(agent_id),
            data_dir=data_dir,
            override=overrides.get(agent_id),
        )
    return agents


def build_store_config(
    *,
    data_dir: str,
    mail_root: Path | None = None,
) -> dict[str, Any]:
    root = mailbus_root(mail_root)
    fragments = load_config_fragments(mail_root=root)
    overrides = fragments.pop("_agent_overrides", {}) or {}

    config: dict[str, Any] = {
        "project": "ziyan-mailbus",
        "version": MAILBUS_VERSION,
        "data_dir": data_dir.replace("\\", "/"),
        "ack_timeout": DEFAULT_ACK_TIMEOUT,
        "max_retries": DEFAULT_MAX_RETRIES,
        "archive_days": DEFAULT_ARCHIVE_DAYS,
        "archive_max_messages": DEFAULT_ARCHIVE_MAX_MESSAGES,
        "agents": {},
    }
    _deep_merge(config, fragments)
    config["data_dir"] = data_dir.replace("\\", "/")
    config["version"] = config.get("version") or MAILBUS_VERSION
    config["agents"] = build_agents_from_registry(
        data_dir=data_dir,
        mail_root=root,
        overrides=overrides,
    )
    return config


def ensure_runtime_dirs(data_dir: str | Path) -> None:
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    for rel in RUNTIME_SUBDIRS:
        (root / rel).mkdir(parents=True, exist_ok=True)


def mirror_workflows_to_store(data_dir: str | Path, *, mail_root: Path | None = None) -> list[str]:
    """Copy mail/config/workflows/* → store/workflows/ (registry SoT)."""
    root = mailbus_root(mail_root)
    src_dir = root / "config" / "workflows"
    if not src_dir.is_dir():
        return []
    dest = Path(data_dir) / "workflows"
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for src in sorted(src_dir.glob("*.json")):
        shutil.copy2(src, dest / src.name)
        copied.append(f"workflows/{src.name}")
    return copied


def mirror_rule_schemas_to_store(data_dir: str | Path, *, mail_root: Path | None = None) -> list[str]:
    """Copy mail/rules/schemas/*.json → store/rules/ (validator SoT)."""
    root = mailbus_root(mail_root)
    schema_dir = root / "rules" / "schemas"
    if not schema_dir.is_dir():
        return []
    dest = Path(data_dir) / "rules"
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for src in sorted(schema_dir.glob("*.json")):
        shutil.copy2(src, dest / src.name)
        copied.append(f"rules/{src.name}")
    return copied


def mirror_dispatch_seed(data_dir: str | Path, *, mail_root: Path | None = None) -> list[str]:
    """Copy mail/config/dispatch/* → store/dispatch/."""
    root = mailbus_root(mail_root)
    src_dir = root / "config" / "dispatch"
    if not src_dir.is_dir():
        return []
    dest = Path(data_dir) / "dispatch"
    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for src in sorted(src_dir.glob("*.json")):
        shutil.copy2(src, dest / src.name)
        copied.append(f"dispatch/{src.name}")
    return copied


def mirror_billing_schemas(data_dir: str | Path, *, mail_root: Path | None = None) -> list[str]:
    """Ensure store/billing/ has billing-accounts.schema.json from rules/schemas."""
    root = mailbus_root(mail_root)
    src = root / "rules" / "schemas" / "billing-accounts.schema.json"
    if not src.is_file():
        return []
    dest_dir = Path(data_dir) / "billing"
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest_dir / src.name)
    return [f"billing/{src.name}"]


def mirror_org_json(data_dir: str | Path, *, mail_root: Path | None = None) -> list[str]:
    root = mailbus_root(mail_root)
    org_dir = root / "org" / "json"
    dest_dir = Path(data_dir) / "roles" / "json"
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for name in ORG_JSON_MIRROR:
        src = org_dir / name
        if not src.is_file():
            continue
        shutil.copy2(src, dest_dir / name)
        copied.append(name)
    return copied


def write_runtime_seed_files(data_dir: str | Path, agents: dict[str, Any]) -> None:
    from .commands import get_system_message

    root = Path(data_dir)
    json_write(str(root / "sent.json"), {})
    json_write(str(root / "board.json"), {"board": [], "created_at": _now_iso()})
    json_write(
        str(root / "human-queue.json"),
        {"version": "1.0.0", "updated_at": _now_iso(), "items": []},
    )
    json_write(str(root / "leads" / "order-intake.json"), [])

    default_perms = {}
    for name in agents:
        default_perms[name] = {
            "browser": True,
            "cli": True,
            "mailbox": True,
            "bulletin": name in ("lingzhao", "xiaoqi", "lingxiao"),
        }
    json_write(
        str(root / "permission.json"),
        {
            "permissions": default_perms,
            "bulletin": ["lingzhao", "xiaoqi"],
            "updated_at": _now_iso(),
        },
    )

    inbox_root = root / "inbox"
    for agent_id in agents:
        inbox_dir = inbox_root / agent_id
        inbox_dir.mkdir(parents=True, exist_ok=True)
        sys_msg = get_system_message(agent_id)
        sys_msg["system_info"]["registered_agents"] = sorted(agents.keys())
        json_write(
            str(inbox_dir / "inbox.json"),
            {
                "agent": agent_id,
                "has_unread": True,
                "messages": [sys_msg],
                "since": _now_iso(),
            },
        )


def wipe_data_dir(data_dir: str | Path) -> None:
    path = Path(data_dir)
    if path.exists():
        shutil.rmtree(path)


def run_init_store(
    data_dir: str,
    *,
    fresh: bool = False,
    mail_root: Path | str | None = None,
    quiet: bool = False,
) -> int:
    """Initialize or fresh-reset store/ from access + org + config SoT."""
    data_dir = os.path.abspath(data_dir)
    config_path = os.path.join(data_dir, "config.json")

    if os.path.isfile(config_path) and not fresh:
        if not quiet:
            print(f"✗ 配置已存在: {config_path}")
            print("  如需重新初始化，请使用: bus.py init --fresh")
        return 1

    if fresh and Path(data_dir).exists():
        wipe_data_dir(data_dir)

    ensure_runtime_dirs(data_dir)
    config = build_store_config(data_dir=data_dir, mail_root=mail_root)
    json_write(config_path, config)

    copied = mirror_org_json(data_dir, mail_root=mail_root)
    rules_copied = mirror_rules_to_store(data_dir, mail_root=mail_root)
    schema_copied = mirror_rule_schemas_to_store(data_dir, mail_root=mail_root)
    wf_copied = mirror_workflows_to_store(data_dir, mail_root=mail_root)
    dispatch_copied = mirror_dispatch_seed(data_dir, mail_root=mail_root)
    billing_copied = mirror_billing_schemas(data_dir, mail_root=mail_root)
    write_runtime_seed_files(data_dir, config.get("agents") or {})

    if not quiet:
        mode = "fresh" if fresh else "init"
        print(f"✓ init-store ({mode}) 完成")
        print(f"  数据目录: {data_dir}")
        print(f"  配置文件: {config_path}")
        print(f"  agents: {len(config.get('agents') or {})}")
        if rules_copied:
            print(f"  rules mirror: {len(rules_copied)} md → store/rules/")
        if schema_copied:
            print(f"  schemas mirror: {len(schema_copied)} json → store/rules/")
        if wf_copied:
            print(f"  workflows mirror: {', '.join(wf_copied)}")
        if dispatch_copied:
            print(f"  dispatch mirror: {', '.join(dispatch_copied)}")
        if billing_copied:
            print(f"  billing mirror: {', '.join(billing_copied)}")
        if copied:
            print(f"  org 镜像: {', '.join(copied)}")
    return 0
