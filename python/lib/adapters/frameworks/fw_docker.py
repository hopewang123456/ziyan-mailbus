"""Docker 容器家族 Adapter — Hermes / OpenClaw / OpenCode / Dsh。"""
from __future__ import annotations

import re
from typing import Optional

from lib.adapters.container.resolver import resolve_container
from lib.infra.agent_demo import openclaw_gateway_ports, openclaw_state_dirs
from lib.adapters.frameworks.base import BaseAdapter
from lib.adapters.frameworks.fw_util import (
    _flag_value, _join, _push_cwd, model_flag, shlex_quote,
)


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
    STATE_DIRS = openclaw_state_dirs() or {
        "agent-m": "/workspace/data/.openclaw-agent-m",
        "agent-l": "/workspace/data/.openclaw-agent-l",
    }
    GATEWAY_PORTS = openclaw_gateway_ports() or {
        "agent-m": 18789,
        "agent-l": 18790,
    }

    @classmethod
    def resolve_gateway_port(cls, agent_name: str, browser_cfg: dict | None = None) -> int:
        browser_cfg = browser_cfg or {}
        from lib.adapters.config.launch_ports import resolve_port

        port = resolve_port(
            agent_name,
            {"type": "openclaw"},
            browser_cfg,
            group="openclaw_gateway",
        )
        if port is not None:
            return port
        return int(cls.GATEWAY_PORTS.get(agent_name, 18789))

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


class OpenCodeAdapter(BaseAdapter):
    """OpenCode：`opencode run` 非交互，须 --dangerously-skip-permissions，独立容器。"""

    type_name = "opencode"
    container_service = "opencode"
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
        cwd = _push_cwd(agent_cfg, default="/workspace/opencode")
        if cwd == "/mailbus/store":
            cwd = "/workspace/opencode"
        # 交互 TUI：不要带 -m（易非交互秒退）；默认进 Members 对应的工作区挂载
        return f"docker exec -it {container} bash -lc 'cd {cwd} && exec opencode'"

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


class DshAdapter(BaseAdapter):
    """DeepSeek Harness (dsh)：`docker exec <container> dsh --profile headless 'MSG'`。

    非交互单次 headless 执行，完成任务后由 dsh 侧写 D1 step-result；
    mailbus 复用 ack + step-result 验收，不在此新造验收。
    """

    type_name = "dsh"
    container_service = "dsh"
    mark_processing_on_task_push = True

    def push_timeout_seconds(self, *, pipeline: bool = False, agent_cfg: dict | None = None) -> int:
        if agent_cfg and agent_cfg.get("push_timeout_seconds") is not None:
            return int(agent_cfg["push_timeout_seconds"])
        return 900 if pipeline else 300

    def _profile(self, agent_name: str, agent_cfg: dict) -> str:
        return agent_cfg.get("profile") or "headless"

    def build_push_cli(self, agent_name, agent_cfg, agent_types, model_alias=None) -> str:
        container = resolve_container(agent_cfg, agent_name, self.container_service)
        profile = self._profile(agent_name, agent_cfg)
        mflag = model_flag(agent_cfg, agent_types, self.type_name, model_alias)
        return _join(
            f"docker exec {container} dsh --profile {profile}",
            mflag,
            "'MSG'",
        )

    def build_interactive_cli(self, agent_name, agent_cfg, agent_types) -> str:
        container = resolve_container(agent_cfg, agent_name, self.container_service)
        profile = self._profile(agent_name, agent_cfg)
        return f"docker exec -it {container} dsh --profile {profile}"

    def cli_active_in_ps(self, agent_name, agent_cfg, ps_output) -> bool:
        # 常驻 web 进程为 `dsh web`；push 为 `dsh --profile ...`，据此区分
        noise = ("grep", "tail -f /dev/null", " dsh web", "dsh web")
        for line in ps_output.splitlines():
            low = line.lower()
            if any(n in low for n in noise):
                continue
            if re.search(r"\bdsh\b", line) and "--profile" in line:
                return True
        return False

    def validate(self, agent_name, agent_cfg) -> list[str]:
        return []
