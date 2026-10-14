"""宿主/降级家族 Adapter — ClaudeCode / Zcode / Cursor / A2A Remote / None。"""
from __future__ import annotations

import os
from typing import Optional

from lib.adapters.frameworks.base import BaseAdapter
from lib.adapters.frameworks.fw_util import model_flag, shlex_quote


class ClaudeCodeAdapter(BaseAdapter):
    """Claude Code CLI：宿主机 `claude -p` headless，文件任务推送，非 Docker。"""

    type_name = "claude_code"
    container_service = ""
    mark_processing_on_task_push = True

    def push_timeout_seconds(self, *, pipeline: bool = False, agent_cfg: dict | None = None) -> int:
        if agent_cfg and agent_cfg.get("push_timeout_seconds") is not None:
            return int(agent_cfg["push_timeout_seconds"])
        return 900 if pipeline else 300

    def build_push_cli(self, agent_name, agent_cfg, agent_types, model_alias=None, *, data_dir=None) -> str:
        from lib.adapters.frameworks.claude_launch import build_push_command

        return build_push_command(
            agent_name, agent_cfg, agent_types, model_alias, data_dir=data_dir,
        )

    def build_interactive_cli(self, agent_name, agent_cfg, agent_types) -> str:
        from lib.adapters.frameworks.claude_launch import build_interactive_command

        return build_interactive_command(agent_name, agent_cfg, agent_types)

    def cli_active_in_ps(self, agent_name, agent_cfg, ps_output) -> bool:
        from lib.adapters.frameworks.claude_launch import host_cli_active

        return host_cli_active(ps_output)

    def validate(self, agent_name, agent_cfg) -> list[str]:
        return []


class ZcodeAdapter(BaseAdapter):
    """ZCode CLI：宿主机 `zcode -p` headless（GLM 内置后端，Z.AI OAuth），非 Docker。

    隔离经 ZCODE_HOME per-agent（实测 OAuth 认证跟随）；二进制缺失时 direct
    返回 None → 消息留 pending 待宿主 scan（与 claude PowerShell-skip 同机制）。
    """

    type_name = "zcode"
    container_service = ""
    mark_processing_on_task_push = True

    def push_timeout_seconds(self, *, pipeline: bool = False, agent_cfg: dict | None = None) -> int:
        if agent_cfg and agent_cfg.get("push_timeout_seconds") is not None:
            return int(agent_cfg["push_timeout_seconds"])
        return 900 if pipeline else 300

    def build_push_cli(self, agent_name, agent_cfg, agent_types, model_alias=None, *, data_dir=None):
        from lib.adapters.frameworks.zcode_launch import build_push_command

        return build_push_command(agent_name, agent_cfg, agent_types, data_dir=data_dir or "")

    def build_interactive_cli(self, agent_name, agent_cfg, agent_types) -> str:
        from lib.adapters.frameworks.zcode_launch import build_interactive_command

        return build_interactive_command(agent_name, agent_cfg)

    def cli_active_in_ps(self, agent_name, agent_cfg, ps_output) -> bool:
        from lib.adapters.frameworks.zcode_launch import host_cli_active

        return host_cli_active(ps_output)

    def validate(self, agent_name, agent_cfg) -> list[str]:
        return []


class NoneAdapter(BaseAdapter):
    type_name = "none"
    allow_no_push_cli = True

    def build_push_cli(self, agent_name, agent_cfg, agent_types, model_alias=None) -> str:
        return ""

    def build_interactive_cli(self, agent_name, agent_cfg, agent_types) -> str:
        return ""


class A2ARemoteAdapter(BaseAdapter):
    """远程 A2A agent — 派发走 TransportRouter，不经 CLI push。"""

    type_name = "a2a_remote"
    supports_auto_ack = False
    mark_processing_on_task_push = False
    allow_no_push_cli = True

    def can_deliver_a2a(self, agent_cfg: dict) -> bool:
        from lib.core.a2a.delivery import can_deliver_a2a

        return can_deliver_a2a(agent_cfg)

    def build_push_cli(self, agent_name, agent_cfg, agent_types, model_alias=None, *, data_dir=None) -> str:
        return ""

    def build_interactive_cli(self, agent_name, agent_cfg, agent_types) -> str:
        return ""

    def validate(self, agent_name, agent_cfg) -> list[str]:
        errs: list[str] = []
        endpoint = agent_cfg.get("endpoint") or {}
        if not (endpoint.get("base_url") or endpoint.get("rpc_url")):
            errs.append(f"{agent_name}: a2a_remote 缺少 endpoint.base_url")
        if not agent_cfg.get("supportedInterfaces"):
            errs.append(f"{agent_name}: a2a_remote 缺少 supportedInterfaces")
        return errs


class CursorAdapter(BaseAdapter):
    """Cursor agent CLI — cursor-agent / agent when available; else file_bus + D1."""

    type_name = "cursor"
    supports_auto_ack = False
    mark_processing_on_task_push = True
    allow_no_push_cli = True

    def build_push_cli(self, agent_name, agent_cfg, agent_types, model_alias=None, *, data_dir=None) -> str:
        # Prefer Cursor Agent CLI if present on PATH
        import shutil

        bin_name = shutil.which("cursor-agent") or shutil.which("agent")
        if not bin_name:
            return ""
        model = model_flag(agent_cfg, agent_types, "cursor", model_alias) if model_alias else ""
        # Message placeholder filled by pusher
        return f"{bin_name} -p 'MSG'" + (f" {model}" if model else "")

    def build_interactive_cli(self, agent_name, agent_cfg, agent_types) -> str:
        import shutil

        bin_name = shutil.which("cursor-agent") or shutil.which("agent") or "cursor-agent"
        return bin_name

    def validate(self, agent_name, agent_cfg) -> list[str]:
        return []
