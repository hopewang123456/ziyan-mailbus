"""文件工单家族 Adapter — Cline / Codex（msg-files 工单 + msg-results 验收）。"""
from __future__ import annotations

import re
from typing import Optional

from lib.adapters.container.resolver import resolve_container
from lib.adapters.frameworks.base import BaseAdapter, PUSH_TIMEOUT_DEFAULT, PUSH_TIMEOUT_PIPELINE
from lib.adapters.frameworks.fw_util import (
    _flag_value, _join, _push_cwd, model_flag, provider_flag, shlex_quote,
)


class ClineAdapter(BaseAdapter):
    """Cline：positional prompt 非交互 act 模式，独立容器，不走 Hermes profile。"""

    type_name = "cline"
    container_service = "codex-web"
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


class CodexAdapter(BaseAdapter):
    """Codex CLI：`codex exec` 非交互，文件任务推送，独立容器。"""

    type_name = "codex"
    container_service = "codex-web"
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
