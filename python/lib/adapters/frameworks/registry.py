"""Agent 类型适配层 — 注册表与分派 API（Adapter 类见 fw_* 家族文件）。

Hermes / OpenClaw / Cline / OpenCode / Codex CLI / Claude Code / A2A Remote 等
**平级 Agent 架构**，push / interactive CLI、HTTP 交付均在 Adapter 层集中维护。

mailbus Core 只认 agent_id + role_type；新增框架 = 新 Adapter 类 + ADAPTERS 注册。
规范: access/{framework}/adapter/SPEC.md
"""
from __future__ import annotations

import re
import subprocess
from typing import Optional

from lib.adapters.container.resolver import (  # noqa: F401 — re-export for callers
    container_for_service,
    container_prefix,
    resolve_container,
)
from lib.infra.agent_demo import openclaw_gateway_ports, openclaw_state_dirs  # noqa: F401
from lib.adapters.frameworks.spec import FRAMEWORKS
from lib.adapters.frameworks.base import (  # noqa: F401 — re-export for callers
    BaseAdapter, PUSH_TIMEOUT_DEFAULT, PUSH_TIMEOUT_PIPELINE,
)
from lib.adapters.frameworks.fw_util import (  # noqa: F401
    model_flag, provider_flag, _join, _flag_value, _push_cwd, shlex_quote,
)
from lib.adapters.frameworks.fw_docker import (
    DshAdapter, HermesAdapter, HermesProfileAdapter, OpenClawAdapter, OpenCodeAdapter,
)
from lib.adapters.frameworks.fw_filetask import ClineAdapter, CodexAdapter
from lib.adapters.frameworks.fw_host import (
    A2ARemoteAdapter, ClaudeCodeAdapter, CursorAdapter, NoneAdapter, ZcodeAdapter,
)


# Cline / OpenCode 与 Hermes / OpenClaw 推送语义不同：
# - Hermes/OpenClaw: -q/--message 单次查询，notice 可 auto_ack
# - Cline/OpenCode:  positional prompt + run 子命令，须等 CLI 落盘 msg-results，永不 auto_ack
# Docker compose 服务名 → 推荐 agent type（派生自 FRAMEWORKS.docker_services 反转）
DOCKER_SERVICE_TYPE = {
    svc: fw for fw, spec in FRAMEWORKS.items() for svc in spec.docker_services
}

# type=cline 仅保留 WSL 直连场景；Docker 内 codex 服务应使用 codex


ADAPTERS: dict[str, BaseAdapter] = {
    "hermes": HermesAdapter(),
    "hermes_profile": HermesProfileAdapter(),
    "openclaw": OpenClawAdapter(),
    "cline": ClineAdapter(),
    "opencode": OpenCodeAdapter(),
    "codex": CodexAdapter(),
    "claude_code": ClaudeCodeAdapter(),
    "a2a_remote": A2ARemoteAdapter(),
    "cursor": CursorAdapter(),
    "dsh": DshAdapter(),
    "zcode": ZcodeAdapter(),
    "none": NoneAdapter(),
}


def register_framework(name: str, adapter: BaseAdapter, *, replace: bool = False) -> None:
    """S4 load-time hook — register an adapter (no hot-reload)."""
    key = (name or "").strip().lower()
    if not key:
        raise ValueError("empty framework name")
    if not isinstance(adapter, BaseAdapter):
        raise TypeError("adapter must be a BaseAdapter instance")
    if key in ADAPTERS and not replace:
        raise ValueError(f"framework already registered: {key}")
    ADAPTERS[key] = adapter


def unregister_framework(name: str) -> bool:
    """Remove a previously registered framework (tests / teardown)."""
    key = (name or "").strip().lower()
    if not key or key not in ADAPTERS:
        return False
    del ADAPTERS[key]
    return True


def list_frameworks() -> list[str]:
    return sorted(ADAPTERS)


def get_adapter(agent_type: str) -> Optional[BaseAdapter]:
    return ADAPTERS.get(agent_type or "none")



def resolve_push_cli(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    model_alias: Optional[str] = None,
    *,
    pipeline: bool = False,
    data_dir: str = "",
) -> str:
    """mailbus 推送用 CLI（非 TTY）。"""
    atype = agent_cfg.get("type", "none")

    adapter = get_adapter(atype)
    if adapter:
        # kwargs 分派由 FRAMEWORKS spec 声明（pass_pipeline / needs_data_dir），
        # 不再 per-type 特判——spec 与 Adapter.build_push_cli 签名的耦合由
        # tests/test_framework_spec.py 的签名一致性测试钉住。
        spec = FRAMEWORKS.get(atype)
        if spec and spec.pass_pipeline:
            return adapter.build_push_cli(
                agent_name, agent_cfg, agent_types, model_alias, pipeline=pipeline,
            )
        if spec and spec.needs_data_dir and data_dir:
            return adapter.build_push_cli(
                agent_name, agent_cfg, agent_types, model_alias, data_dir=data_dir,
            )
        return adapter.build_push_cli(agent_name, agent_cfg, agent_types, model_alias)

    # agent_types.push 模板 fallback
    atype = agent_cfg.get("type", "none")
    tmpl = agent_types.get(atype, {}).get("push", "")
    if not tmpl:
        return ""
    cmd = tmpl
    profile = agent_cfg.get("profile", "") or agent_cfg.get("agent", "")
    cmd = cmd.replace("PROFILE", profile).replace("AGENT", agent_cfg.get("agent", ""))
    mflag = model_flag(agent_cfg, agent_types, atype, model_alias)
    provider = provider_flag(agent_cfg, agent_types, atype, model_alias)
    if mflag:
        cmd = cmd.replace("MODEL", mflag).replace("--model MODEL", mflag)
    else:
        cmd = cmd.replace("--model MODEL", "").replace("MODEL", "")
    if provider:
        cmd = cmd.replace("PROVIDER", provider).replace("--provider PROVIDER", provider)
    else:
        cmd = cmd.replace("--provider PROVIDER", "").replace("PROVIDER", "")
    if mflag and "hermes chat" in cmd and "--model " not in cmd and " --yolo" in cmd:
        cmd = cmd.replace(" --yolo", f" {mflag} --yolo", 1)
    return cmd.strip()


def resolve_interactive_cli(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    *,
    data_dir: str | None = None,
) -> str:
    """人工 launch / TTY 窗口用 CLI。"""
    if agent_cfg.get("type") == "claude_code":
        from lib.adapters.frameworks.claude_launch import build_interactive_command, _default_data_dir

        dd = data_dir or _default_data_dir()
        return build_interactive_command(agent_name, agent_cfg, agent_types, data_dir=dd)
    adapter = get_adapter(agent_cfg.get("type", "none"))
    if adapter:
        return adapter.build_interactive_cli(agent_name, agent_cfg, agent_types)
    return ""


def agent_cli_active(agent_name: str, agents: dict) -> bool:
    """容器内或宿主机是否仍有该 agent 的任务 CLI 在跑。"""
    return agent_cli_active_for(agent_name, agents)


def agent_cli_active_for(
    agent_name: str,
    agents: dict,
    *,
    msg_id: str = "",
    task_id: str = "",
) -> bool:
    """按 msg_id / task_id 精确判断 CLI 是否仍为该工单占用（Codex 单槽）。"""
    agent_cfg = agents.get(agent_name) or {}
    adapter = get_adapter(agent_cfg.get("type", ""))
    if not adapter:
        return False
    use_precise = bool(msg_id or task_id) and hasattr(adapter, "cli_active_in_ps_for")
    if not adapter.container_service:
        from lib.adapters.frameworks.claude_launch import host_ps_output

        ps = host_ps_output()
        if use_precise:
            return adapter.cli_active_in_ps_for(
                agent_name, agent_cfg, ps, msg_id=msg_id, task_id=task_id,
            )
        return adapter.cli_active_in_ps(agent_name, agent_cfg, ps)
    docker_svc = (agent_cfg.get("docker") or {}).get("service")
    default_svc = docker_svc or adapter.container_service or agent_name
    container = resolve_container(agent_cfg, agent_name, default_svc)
    if not container:
        return False
    from lib.adapters.ops.docker_probe import docker_exec_ps

    ps = docker_exec_ps(container)
    if not ps:
        return False
    if use_precise:
        return adapter.cli_active_in_ps_for(
            agent_name, agent_cfg, ps, msg_id=msg_id, task_id=task_id,
        )
    return adapter.cli_active_in_ps(agent_name, agent_cfg, ps)


def validate_agents(agents: dict, agent_types: dict | None = None) -> list[str]:
    """校验全部 agent — 基于适配层生成 CLI，不要求 launch.cli.command。"""
    errors: list[str] = []
    hermes_profiles: list[str] = []
    agent_types = agent_types or {}

    for name, cfg in agents.items():
        atype = cfg.get("type", "")
        display = cfg.get("name") or name
        adapter = get_adapter(atype)

        if not adapter:
            errors.append(f"{name} ({display}): 未知 type={atype}")
            continue

        errors.extend(adapter.validate(name, cfg))

        if atype == "hermes_profile":
            profile = cfg.get("profile") or name
            hermes_profiles.append(profile)

        docker_svc = (cfg.get("docker") or {}).get("service") or name
        expected = DOCKER_SERVICE_TYPE.get(docker_svc)
        if expected and atype != expected and not (atype == "hermes_profile" and expected == "hermes_profile"):
            if atype == "cline" and expected == "codex":
                errors.append(
                    f"{name} ({display}): type=cline 但 docker.service={docker_svc} "
                    f"在 compose 中已切 codex-agent，请改为 type=codex"
                )
            elif atype != expected:
                errors.append(
                    f"{name} ({display}): type={atype} 与 docker.service={docker_svc} "
                    f"推荐 type={expected} 不一致"
                )

        push_cmd = resolve_push_cli(name, cfg, agent_types)
        if not push_cmd and atype != "none" and not getattr(adapter, "allow_no_push_cli", False):
            errors.append(f"{name} ({display}): 适配层无法生成 push CLI")
        elif push_cmd and "--skills" in push_cmd:
            errors.append(f"{name} ({display}): push CLI 含 --skills")

    if len(hermes_profiles) != len(set(hermes_profiles)):
        errors.append("hermes profile 名重复")

    return errors


def push_timeout_for(agent_cfg: dict, *, pipeline: bool = False) -> int:
    """按适配层返回 CLI communicate 超时（秒）。"""
    adapter = get_adapter(agent_cfg.get("type", ""))
    if adapter:
        return adapter.push_timeout_seconds(pipeline=pipeline, agent_cfg=agent_cfg)
    return PUSH_TIMEOUT_PIPELINE if pipeline else PUSH_TIMEOUT_DEFAULT


def store_path_for_agent(data_dir: str, path: str, agent_cfg: dict) -> str:
    """容器内 agent 推送/工单使用 /mailbus/store 路径。"""
    adapter = get_adapter((agent_cfg or {}).get("type", ""))
    if adapter and adapter.container_service:
        from lib.infra.utils import to_container_store_path

        return to_container_store_path(data_dir, path)
    return path


def should_mark_processing_on_push(agent_cfg: dict, msg_entry: dict) -> bool:
    """Cline/OpenCode/Codex 推送 task 成功后进入 processing（等 msg-results，不 auto_ack）。"""
    adapter = get_adapter(agent_cfg.get("type", ""))
    if not adapter or not adapter.mark_processing_on_task_push:
        return False
    mtype = (msg_entry or {}).get("type", "notice")
    action = (msg_entry or {}).get("action") or {}
    execute = action.get("execute", mtype == "task") if isinstance(action, dict) else True
    return mtype == "task" and execute


def type_supports_auto_ack(agent_type: str) -> bool:
    adapter = get_adapter(agent_type or "")
    return bool(adapter and adapter.supports_auto_ack)


# 支持直接 docker exec 弹交互终端的 agent atype 集合
_INTERACTIVE_CLI_TYPES = frozenset({
    "opencode", "codex", "openclaw", "hermes", "hermes_profile",
})


def supports_interactive_cli(atype: str) -> bool:
    """该 atype 是否支持 `docker exec -it <container> <cli>` 直弹。"""
    return (atype or "") in _INTERACTIVE_CLI_TYPES


def build_interactive_cli_command(atype: str, container: str, profile: str) -> str:
    """组装 `docker exec -it <container> <agent-cli>` 命令字符串。

    由 API 层（handlers_system.py）在已解析 container 名后调用；
    registry 负责把 atype→CLI 字符串的 if/elif 链收敛到这里，handler 只剩调度。

    返回字符串用于 `enqueue_launch_queue` 入队到 watchdog 弹出终端；
    不返回 None — 调用方应在 container 非空时再调。
    """
    if not container:
        raise ValueError("container is required")
    profile = profile or ""
    if atype == "hermes_profile":
        return f"docker exec -it {container} hermes -p {profile} chat --yolo"
    if atype == "hermes":
        return f"docker exec -it {container} hermes -p {profile} chat"
    if atype == "openclaw":
        return f"docker exec -it {container} openclaw tui"
    if atype == "codex":
        return f"docker exec -it {container} codex"
    if atype == "opencode":
        return f'docker exec -it {container} bash -c "cd /workspace/opencode && opencode"'
    raise ValueError(f"unsupported interactive-cli atype: {atype!r}")
