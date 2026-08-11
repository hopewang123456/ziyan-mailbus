"""Integrations port — model router / ollama / plugin registry / agentmemory."""
from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class IntegrationsPort(Protocol):
    """Minimal integrations surface for application / composition."""

    def pick_model_alias(
        self,
        msg: Any,
        agent_name: str,
        agent_cfg: Mapping[str, Any],
        *,
        primary_task_id: str = "",
        config: Mapping[str, Any] | None = None,
        data_dir: str = "",
        routing_out: dict | None = None,
    ) -> str: ...

    def resolve_ollama_settings(
        self,
        config: Mapping[str, Any] | None = None,
        data_dir: str = "",
    ) -> dict[str, Any]: ...

    def is_ollama_ready(self, **kwargs: Any) -> bool: ...

    def get_integration(self, name: str) -> Any: ...

    def list_integrations(self) -> list[dict[str, str]]: ...

    def agentmemory_url(self, *, mail_root: str | None = None) -> str: ...

    def is_no_llm_notice(self, msg: Any) -> bool: ...

    def tier_pro(self) -> str: ...

    def tier_ollama(self) -> str: ...

    def is_pro_allowed(self, agent_cfg: Mapping[str, Any]) -> bool: ...

    def post_json_with_wsl_fallback(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, Any] | None = None,
        *,
        timeout: int = 30,
    ) -> tuple[int, Any]: ...

    def invoke_tool(
        self,
        data_dir: str,
        *,
        agent_id: str,
        tool_id: str,
        inputs: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]: ...

    def archive_agentmemory(self, data_dir: str, agent_id: str) -> str: ...

    def write_mcp_mount_hint(self, data_dir: str, agent_id: str) -> str: ...

    def clear_mcp_mount_hint(self, data_dir: str, agent_id: str) -> None: ...
