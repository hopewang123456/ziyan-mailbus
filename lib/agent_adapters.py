"""Agent 类型适配层 — 同类型 agent 共用指令模板，config 只存参数。

Hermes / OpenClaw / Cline / OpenCode / Codex CLI / Claude Code / A2A Remote 等
**平级 Agent 架构**，push / interactive CLI、HTTP 交付均在 Adapter 层集中维护。

mailbus Core 只认 agent_id + role_type；新增框架 = 新 Adapter 类 + ADAPTERS 注册。
规范: mail/access/{framework}/adapter/SPEC.md · mail/docs/agent-adapter-layer.md
"""
from __future__ import annotations

import os
import re
import subprocess
from typing import Optional

from .access_adapters import load_adapter_spec

# ── 容器解析 ──────────────────────────────────────────────────────


def container_prefix() -> str:
    return os.environ.get("MAILBUS_CONTAINER_PREFIX", "docker-agents")


def container_for_service(service: str) -> str:
    env_key = f"MAILBUS_CONTAINER_{service.upper().replace('-', '_')}"
    if os.environ.get(env_key):
        return os.environ[env_key]
    return f"{container_prefix()}-{service}-1"


def resolve_container(agent_cfg: dict, agent_name: str, default_service: str) -> str:
    docker_cfg = agent_cfg.get("docker") or {}
    return (
        docker_cfg.get("container")
        or os.environ.get(f"MAILBUS_CONTAINER_{agent_name.upper()}")
        or container_for_service(default_service)
    )


# ── 模型参数 ──────────────────────────────────────────────────────


def model_flag(agent_cfg: dict, agent_types: dict, atype: str, model_alias: Optional[str]) -> str:
    models_map = agent_types.get("models", {})
    agent_models = agent_cfg.get("models", [])
    # 路由选了 pro 但 agent 未装备 → 回落 flash，避免 Hermes profile 默认走 v4-pro
    if model_alias and model_alias not in agent_models and agent_models:
        model_alias = agent_models[0]
    if not model_alias:
        model_alias = agent_models[0] if agent_models else None
    if model_alias and model_alias in models_map:
        return models_map[model_alias].get(atype, "") or ""
    return ""


def provider_flag(agent_cfg: dict, agent_types: dict, atype: str, model_alias: Optional[str]) -> str:
    final = (agent_cfg.get("provider") or "").strip()
    if final:
        return final
    models_map = agent_types.get("models", {})
    agent_models = agent_cfg.get("models", [])
    if model_alias and model_alias not in agent_models and agent_models:
        model_alias = agent_models[0]
    if not model_alias:
        model_alias = agent_models[0] if agent_models else None
    if model_alias and model_alias in models_map:
        return models_map[model_alias].get(atype, "") or ""
    return ""


def _join(*parts: str) -> str:
    return " ".join(p for p in parts if p).strip()


def _flag_value(raw: str, *prefixes: str) -> str:
    """从 '--provider foo' / '-P foo' 提取值。"""
    text = (raw or "").strip()
    for prefix in prefixes:
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    return text


def _push_cwd(agent_cfg: dict, default: str = "/mailbus/store") -> str:
    push = agent_cfg.get("push") or {}
    return (push.get("cwd") or agent_cfg.get("cwd") or default).strip()


# Cline / OpenCode 与 Hermes / OpenClaw 推送语义不同：
# - Hermes/OpenClaw: -q/--message 单次查询，notice 可 auto_ack
# - Cline/OpenCode:  positional prompt + run 子命令，须等 CLI 落盘 msg-results，永不 auto_ack
# Docker compose 服务名 → 推荐 agent type（lingxiao/lingjian 已迁移 codex）
DOCKER_SERVICE_TYPE = {
    "lingxiao": "codex",
    "lingjian": "codex",
    "dali": "opencode",
    "hermes": "hermes_profile",
    "openclaw": "openclaw",
}

# type=cline 仅保留 WSL 直连场景；Docker 内 lingxiao/lingjian 应使用 codex
CLINE_LEGACY_AGENTS = frozenset()
PUSH_TIMEOUT_DEFAULT = 120
PUSH_TIMEOUT_PIPELINE = 600


# ── 适配器 ────────────────────────────────────────────────────────


class BaseAdapter:
    type_name: str = ""
    container_service: str = ""
    supports_auto_ack: bool = False
    mark_processing_on_task_push: bool = False

    def push_timeout_seconds(self, *, pipeline: bool = False, agent_cfg: dict | None = None) -> int:
        if agent_cfg and agent_cfg.get("push_timeout_seconds") is not None:
            return int(agent_cfg["push_timeout_seconds"])
        return PUSH_TIMEOUT_PIPELINE if pipeline else PUSH_TIMEOUT_DEFAULT

    def build_push_cli(
        self,
        agent_name: str,
        agent_cfg: dict,
        agent_types: dict,
        model_alias: Optional[str] = None,
    ) -> str:
        raise NotImplementedError

    def build_interactive_cli(
        self,
        agent_name: str,
        agent_cfg: dict,
        agent_types: dict,
    ) -> str:
        raise NotImplementedError

    def cli_active_in_ps(self, agent_name: str, agent_cfg: dict, ps_output: str) -> bool:
        return False

    def validate(self, agent_name: str, agent_cfg: dict) -> list[str]:
        return []


class HermesProfileAdapter(BaseAdapter):
    type_name = "hermes_profile"
    container_service = "hermes"
    supports_auto_ack = True
    mark_processing_on_task_push = True

    def _profile(self, agent_name: str, agent_cfg: dict) -> str:
        return agent_cfg.get("profile") or agent_name

    def build_push_cli(self, agent_name, agent_cfg, agent_types, model_alias=None) -> str:
        container = resolve_container(agent_cfg, agent_name, self.container_service)
        profile = self._profile(agent_name, agent_cfg)
        mflag = model_flag(agent_cfg, agent_types, self.type_name, model_alias)
        return _join(
            f"docker exec {container} hermes chat --profile {profile}",
            mflag,
            "--yolo -q 'MSG' -Q",
        )

    def build_interactive_cli(self, agent_name, agent_cfg, agent_types) -> str:
        container = resolve_container(agent_cfg, agent_name, self.container_service)
        profile = self._profile(agent_name, agent_cfg)
        return f"docker exec -it {container} hermes chat --profile {profile} --yolo"

    def cli_active_in_ps(self, agent_name, agent_cfg, ps_output) -> bool:
        profile = self._profile(agent_name, agent_cfg)
        pat = re.compile(rf"hermes chat.*--profile\s+{re.escape(profile)}\b")
        return any(
            pat.search(line) and "dashboard" not in line
            for line in ps_output.splitlines()
        )

    def validate(self, agent_name, agent_cfg) -> list[str]:
        errors = []
        profile = self._profile(agent_name, agent_cfg)
        if not profile:
            errors.append(f"{agent_name}: hermes_profile 缺少 profile")
        return errors


class HermesAdapter(HermesProfileAdapter):
    type_name = "hermes"

    def _profile(self, agent_name: str, agent_cfg: dict) -> str:
        return agent_cfg.get("profile") or ""

    def build_push_cli(self, agent_name, agent_cfg, agent_types, model_alias=None) -> str:
        container = resolve_container(agent_cfg, agent_name, self.container_service)
        mflag = model_flag(agent_cfg, agent_types, self.type_name, model_alias)
        base = f"docker exec {container} hermes chat"
        if self._profile(agent_name, agent_cfg):
            base += f" --profile {self._profile(agent_name, agent_cfg)}"
        return _join(base, mflag, "--yolo -q 'MSG' -Q")


class OpenClawAdapter(BaseAdapter):
    type_name = "openclaw"
    container_service = "openclaw"
    supports_auto_ack = True
    # mailbus agent key → OpenClaw 独立 state 目录（同容器多 profile）
    STATE_DIRS = {
        "xiaoqi": "/workspace/data/.openclaw-xiaoqi",
        "yige": "/workspace/data/.openclaw-yige",
    }

    def _agent_id(self, agent_name: str, agent_cfg: dict) -> str:
        return agent_cfg.get("agent") or agent_name

    def _state_dir(self, agent_name: str, agent_cfg: dict) -> str:
        return (
            (agent_cfg.get("openclaw") or {}).get("state_dir")
            or self.STATE_DIRS.get(agent_name)
            or "/workspace/data/.openclaw"
        )

    def _session(self, agent_name: str, agent_cfg: dict) -> str:
        cli = (agent_cfg.get("launch") or {}).get("cli") or {}
        return cli.get("session") or self._agent_id(agent_name, agent_cfg)

    def _docker_prefix(self, container: str, state_dir: str) -> str:
        return f"docker exec -e OPENCLAW_STATE_DIR={state_dir} {container}"

    def build_push_cli(self, agent_name, agent_cfg, agent_types, model_alias=None) -> str:
        container = resolve_container(agent_cfg, agent_name, self.container_service)
        agent_id = self._agent_id(agent_name, agent_cfg)
        state_dir = self._state_dir(agent_name, agent_cfg)
        mflag = model_flag(agent_cfg, agent_types, self.type_name, model_alias)
        oc_timeout = self.push_timeout_seconds(pipeline=True, agent_cfg=agent_cfg)
        return _join(
            f"{self._docker_prefix(container, state_dir)} openclaw agent --local --agent {agent_id}",
            "--message 'MSG'",
            mflag,
            f"--timeout {oc_timeout}",
        )

    def build_interactive_cli(self, agent_name, agent_cfg, agent_types) -> str:
        container = resolve_container(agent_cfg, agent_name, self.container_service)
        session = self._session(agent_name, agent_cfg)
        state_dir = self._state_dir(agent_name, agent_cfg)
        return (
            f"{self._docker_prefix(container, state_dir)} openclaw tui --local --session {session}"
        )

    def cli_active_in_ps(self, agent_name, agent_cfg, ps_output) -> bool:
        for line in ps_output.splitlines():
            if "grep" in line:
                continue
            if "openclaw agent" in line or "openclaw tui" in line:
                return True
        return False

    def validate(self, agent_name, agent_cfg) -> list[str]:
        if not self._agent_id(agent_name, agent_cfg):
            return [f"{agent_name}: openclaw 缺少 agent id"]
        return []


class ClineAdapter(BaseAdapter):
    """Cline：positional prompt 非交互 act 模式，独立容器，不走 Hermes profile。"""

    type_name = "cline"
    container_service = "lingxiao"
    mark_processing_on_task_push = True

    def push_timeout_seconds(self, *, pipeline: bool = False, agent_cfg: dict | None = None) -> int:
        if agent_cfg and agent_cfg.get("push_timeout_seconds") is not None:
            return int(agent_cfg["push_timeout_seconds"])
        return 900 if pipeline else 300

    def _provider_id(self, agent_cfg, agent_types, model_alias) -> str:
        raw = provider_flag(agent_cfg, agent_types, self.type_name, model_alias)
        pid = _flag_value(raw, "--provider ", "-P ")
        return pid or agent_cfg.get("provider_id") or "openai-compatible"

    def _model_id(self, agent_cfg, agent_types, model_alias) -> str:
        if agent_cfg.get("model"):
            return str(agent_cfg["model"])
        raw = model_flag(agent_cfg, agent_types, self.type_name, model_alias)
        mid = _flag_value(raw, "--model ", "-m ")
        if mid and not mid.startswith("--provider"):
            return mid
        return "deepseek-chat"

    def build_push_cli(self, agent_name, agent_cfg, agent_types, model_alias=None) -> str:
        container = resolve_container(agent_cfg, agent_name, self.container_service)
        cwd = _push_cwd(agent_cfg)
        provider = self._provider_id(agent_cfg, agent_types, model_alias)
        model = self._model_id(agent_cfg, agent_types, model_alias)
        timeout = self.push_timeout_seconds(pipeline=True, agent_cfg=agent_cfg)
        # prompt 为 positional；与 Hermes -q 不同，须 -P/-m/-t/-c
        inner = _join(
            "cline 'MSG'",
            f"-P {provider}",
            f"-m {model}",
            '-k "${DEEPSEEK_API_KEY:-$OPENAI_API_KEY}"',
            f"-t {timeout}",
            f"-c {cwd}",
            "--auto-approve true",
        )
        return f"docker exec {container} bash -lc {shlex_quote(inner)}"

    def build_interactive_cli(self, agent_name, agent_cfg, agent_types) -> str:
        container = resolve_container(agent_cfg, agent_name, self.container_service)
        provider = self._provider_id(agent_cfg, agent_types, None)
        model = self._model_id(agent_cfg, agent_types, None)
        cwd = _push_cwd(agent_cfg)
        return _join(
            f"docker exec -it {container} bash -lc",
            shlex_quote(_join("cline", f"-P {provider}", f"-m {model}", f"-c {cwd}", "-i")),
        )

    def cli_active_in_ps(self, agent_name, agent_cfg, ps_output) -> bool:
        noise = ("grep", "cline-hub-daemon", "tail -f /dev/null", " dashboard")
        for line in ps_output.splitlines():
            low = line.lower()
            if any(n in low for n in noise):
                continue
            if not re.search(r"\bcline\b", line):
                continue
            # push：positional prompt 或显式 -P/-m/-t；排除常驻 hub
            if re.search(r"(-P\s|--provider\s|-m\s|--model\s|-t\s|--timeout\s|\scline\s+['\"])", line):
                return True
        return False

    def validate(self, agent_name, agent_cfg) -> list[str]:
        return []


class OpenCodeAdapter(BaseAdapter):
    """OpenCode：`opencode run` 非交互，须 --dangerously-skip-permissions，独立容器。"""

    type_name = "opencode"
    container_service = "dali"
    mark_processing_on_task_push = True

    def push_timeout_seconds(self, *, pipeline: bool = False, agent_cfg: dict | None = None) -> int:
        if agent_cfg and agent_cfg.get("push_timeout_seconds") is not None:
            return int(agent_cfg["push_timeout_seconds"])
        return 900 if pipeline else 300

    def _model_flag(self, agent_cfg, agent_types, model_alias) -> str:
        raw = model_flag(agent_cfg, agent_types, self.type_name, model_alias)
        if raw.startswith("--model "):
            return raw
        if agent_cfg.get("model"):
            return f"--model {agent_cfg['model']}"
        return raw or "--model deepseek/deepseek-chat"

    def build_push_cli(self, agent_name, agent_cfg, agent_types, model_alias=None) -> str:
        container = resolve_container(agent_cfg, agent_name, self.container_service)
        cwd = _push_cwd(agent_cfg)
        mflag = self._model_flag(agent_cfg, agent_types, model_alias)
        inner = _join(
            "opencode run 'MSG'",
            "--dangerously-skip-permissions",
            mflag,
            f"--dir {cwd}",
        )
        return f"docker exec {container} bash -lc {shlex_quote(inner)}"

    def build_interactive_cli(self, agent_name, agent_cfg, agent_types) -> str:
        container = resolve_container(agent_cfg, agent_name, self.container_service)
        mflag = self._model_flag(agent_cfg, agent_types, None)
        cwd = _push_cwd(agent_cfg)
        if mflag.startswith("--model "):
            model = mflag.split(" ", 1)[1]
            return f"docker exec -it {container} bash -lc 'cd {cwd} && opencode -m {model.split('/')[-1]}'"
        return f"docker exec -it {container} bash -lc 'cd {cwd} && opencode'"

    def cli_active_in_ps(self, agent_name, agent_cfg, ps_output) -> bool:
        noise = ("grep", "tail -f /dev/null", "node_modules/opencode")
        for line in ps_output.splitlines():
            low = line.lower()
            if any(n in low for n in noise):
                continue
            if re.search(r"\bopencode\s+run\b", line):
                return True
        return False

    def validate(self, agent_name, agent_cfg) -> list[str]:
        return []


class CodexAdapter(BaseAdapter):
    """Codex CLI：`codex exec` 非交互，文件任务推送，独立容器。"""

    type_name = "codex"
    container_service = "lingxiao"
    mark_processing_on_task_push = True

    def push_timeout_seconds(self, *, pipeline: bool = False, agent_cfg: dict | None = None) -> int:
        if agent_cfg and agent_cfg.get("push_timeout_seconds") is not None:
            return int(agent_cfg["push_timeout_seconds"])
        return 900 if pipeline else 300

    def _service(self, agent_name: str, agent_cfg: dict) -> str:
        return (agent_cfg.get("docker") or {}).get("service") or agent_name

    def _codex_sandbox(self, agent_cfg: dict, *, pipeline: bool = False) -> str:
        push = agent_cfg.get("push") or {}
        codex = agent_cfg.get("codex") or {}
        if pipeline:
            sb = push.get("pipeline_sandbox") or codex.get("pipeline_sandbox")
            if sb:
                return str(sb)
        return str(
            push.get("sandbox")
            or codex.get("sandbox")
            or "workspace-write"
        )

    def _model_id(
        self,
        agent_cfg,
        agent_types,
        model_alias,
        *,
        pipeline: bool = False,
    ) -> str:
        push = agent_cfg.get("push") or {}
        if pipeline and push.get("pipeline_model"):
            alias = str(push["pipeline_model"])
            raw = model_flag(agent_cfg, agent_types, self.type_name, alias)
            mid = _flag_value(raw, "--model ", "-m ")
            return mid or alias
        if agent_cfg.get("model"):
            return str(agent_cfg["model"])
        raw = model_flag(agent_cfg, agent_types, self.type_name, model_alias)
        mid = _flag_value(raw, "--model ", "-m ")
        return mid or "deepseek-v4-flash"

    def build_push_cli(
        self, agent_name, agent_cfg, agent_types, model_alias=None, *, pipeline: bool = False,
    ) -> str:
        service = self._service(agent_name, agent_cfg)
        container = resolve_container(agent_cfg, agent_name, service)
        cwd = _push_cwd(agent_cfg)
        model = self._model_id(agent_cfg, agent_types, model_alias, pipeline=pipeline)
        sandbox = self._codex_sandbox(agent_cfg, pipeline=pipeline)
        inner = _join(
            "codex exec",
            "--json --ephemeral --skip-git-repo-check",
            f"--cd {cwd}",
            f"-s {sandbox}",
            '-c \'approval_policy="never"\'',
            f"-m {model}",
            "'MSG'",
        )
        return f"docker exec {container} bash -lc {shlex_quote(inner)}"

    def build_interactive_cli(self, agent_name, agent_cfg, agent_types) -> str:
        service = self._service(agent_name, agent_cfg)
        container = resolve_container(agent_cfg, agent_name, service)
        cwd = _push_cwd(agent_cfg)
        model = self._model_id(agent_cfg, agent_types, None)
        return f"docker exec -it {container} bash -lc {shlex_quote(_join('codex', f'-m {model}', f'--cd {cwd}'))}"

    def cli_active_in_ps(self, agent_name, agent_cfg, ps_output) -> bool:
        noise = ("grep", "tail -f /dev/null", "node_modules/@openai/codex")
        for line in ps_output.splitlines():
            low = line.lower()
            if any(n in low for n in noise):
                continue
            if re.search(r"\bcodex\s+exec\b", line):
                return True
        return False

    def cli_active_in_ps_for(
        self,
        agent_name: str,
        agent_cfg: dict,
        ps_output: str,
        *,
        msg_id: str = "",
        task_id: str = "",
    ) -> bool:
        """Codex 单槽：仅当 ps 行匹配指定 msg_id / task_id 时视为占用。"""
        noise = ("grep", "tail -f /dev/null", "node_modules/@openai/codex")
        needles = [n for n in (msg_id, task_id) if n]
        if not needles:
            return self.cli_active_in_ps(agent_name, agent_cfg, ps_output)
        for line in ps_output.splitlines():
            low = line.lower()
            if any(n in low for n in noise):
                continue
            if not re.search(r"\bcodex\s+exec\b", line):
                continue
            if any(n in line for n in needles):
                return True
        return False

    def validate(self, agent_name, agent_cfg) -> list[str]:
        return []


class ClaudeCodeAdapter(BaseAdapter):
    """Claude Code CLI：宿主机 `claude -p` headless，文件任务推送，非 Docker。"""

    type_name = "claude_code"
    container_service = ""
    mark_processing_on_task_push = True

    def push_timeout_seconds(self, *, pipeline: bool = False, agent_cfg: dict | None = None) -> int:
        if agent_cfg and agent_cfg.get("push_timeout_seconds") is not None:
            return int(agent_cfg["push_timeout_seconds"])
        return 900 if pipeline else 300

    def build_push_cli(self, agent_name, agent_cfg, agent_types, model_alias=None) -> str:
        from .claude_launch import build_push_command

        return build_push_command(agent_name, agent_cfg, agent_types, model_alias)

    def build_interactive_cli(self, agent_name, agent_cfg, agent_types) -> str:
        from .claude_launch import build_interactive_command

        return build_interactive_command(agent_name, agent_cfg, agent_types)

    def cli_active_in_ps(self, agent_name, agent_cfg, ps_output) -> bool:
        from .claude_launch import host_cli_active

        return host_cli_active(ps_output)

    def validate(self, agent_name, agent_cfg) -> list[str]:
        return []


def shlex_quote(s: str) -> str:
    """Shell 单引号转义（供 docker exec bash -lc 使用）。"""
    if not s:
        return "''"
    return "'" + s.replace("'", "'\"'\"'") + "'"


class NoneAdapter(BaseAdapter):
    type_name = "none"

    def build_push_cli(self, agent_name, agent_cfg, agent_types, model_alias=None) -> str:
        return ""

    def build_interactive_cli(self, agent_name, agent_cfg, agent_types) -> str:
        return ""


ADAPTERS: dict[str, BaseAdapter] = {
    "hermes": HermesAdapter(),
    "hermes_profile": HermesProfileAdapter(),
    "openclaw": OpenClawAdapter(),
    "cline": ClineAdapter(),
    "opencode": OpenCodeAdapter(),
    "codex": CodexAdapter(),
    "claude_code": ClaudeCodeAdapter(),
    "none": NoneAdapter(),
}


def get_adapter(agent_type: str) -> Optional[BaseAdapter]:
    return ADAPTERS.get(agent_type or "none")


def framework_adapter_spec(framework: str) -> str:
    """Load access/{fw}/adapter/SPEC.md (v3 SoT)."""
    return load_adapter_spec(framework)


def _legacy_launch_command(agent_cfg: dict) -> str:
    return ((agent_cfg.get("launch") or {}).get("cli") or {}).get("command", "").strip()


def _normalize_push_override(cmd: str, agent_type: str = "") -> str:
    """legacy launch.cli.command → push 形态（按 agent 类型区分）。"""
    cmd = cmd.replace("-it ", " ").replace(" -it", "").strip()
    at = (agent_type or "").strip()
    if at in ("cline", "opencode", "codex", "claude_code"):
        if "'MSG'" not in cmd and "MSG" not in cmd:
            if at == "codex" and "codex exec" not in cmd:
                cmd = f"codex exec 'MSG' {cmd}"
            elif at == "claude_code" and "claude" not in cmd:
                cmd = f"claude -p 'MSG' {cmd}"
            elif at == "claude_code" and "-p" not in cmd and "--print" not in cmd:
                cmd = cmd.replace("claude", "claude -p 'MSG'", 1)
            elif "opencode run" in cmd:
                cmd = cmd.replace("opencode run", "opencode run 'MSG'", 1)
            else:
                cmd = f"{cmd} 'MSG'"
        return cmd.strip()
    if "'MSG'" not in cmd and "MSG" not in cmd:
        if re.search(r"\s--yolo\s*$", cmd):
            cmd = re.sub(r"\s--yolo\s*$", " -q 'MSG' -Q --yolo", cmd)
        else:
            cmd = f"{cmd} -q 'MSG' -Q"
    return cmd.strip()


def resolve_push_cli(
    agent_name: str,
    agent_cfg: dict,
    agent_types: dict,
    model_alias: Optional[str] = None,
    *,
    pipeline: bool = False,
) -> str:
    """mailbus 推送用 CLI（非 TTY）。"""
    atype = agent_cfg.get("type", "none")
    override = _legacy_launch_command(agent_cfg)
    if override:
        return _normalize_push_override(override, atype)

    adapter = get_adapter(atype)
    if adapter:
        if atype == "codex":
            return adapter.build_push_cli(
                agent_name, agent_cfg, agent_types, model_alias, pipeline=pipeline,
            )
        return adapter.build_push_cli(agent_name, agent_cfg, agent_types, model_alias)

    # 极旧配置：agent_types.push 模板 fallback
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
    override = _legacy_launch_command(agent_cfg)
    if override:
        return override
    if agent_cfg.get("type") == "claude_code":
        from .claude_launch import build_interactive_command, _default_data_dir

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
        from .claude_launch import host_ps_output

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
    from .docker_probe import docker_exec_ps

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

        override = _legacy_launch_command(cfg)
        if override:
            if " -it" in override or override.startswith("docker exec -it"):
                errors.append(f"{name} ({display}): legacy launch.cli.command 含 -it")
            if "--skills" in override:
                errors.append(f"{name} ({display}): legacy launch.cli.command 含 --skills")

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
        if not push_cmd and atype != "none":
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
        from .utils import to_container_store_path

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
