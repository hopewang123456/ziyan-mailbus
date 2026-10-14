"""BaseAdapter — 全部框架 Adapter 的基类与推送超时常量。

Adapter 类按家族分置 fw_docker / fw_filetask / fw_host；注册表与
分派 API 见 registry.py。
"""
from __future__ import annotations

from typing import Optional


CLINE_LEGACY_AGENTS = frozenset()
PUSH_TIMEOUT_DEFAULT = 120
PUSH_TIMEOUT_PIPELINE = 600


class BaseAdapter:
    type_name: str = ""
    container_service: str = ""
    supports_auto_ack: bool = False
    mark_processing_on_task_push: bool = False
    # 无 CLI 也可投递（file_bus / A2A 降级）——validate_agents 不因空 push CLI 报错
    allow_no_push_cli: bool = False

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
