"""IntegrationsPort adapter — model_router / ollama / plugin_registry / agentmemory."""
from __future__ import annotations

from typing import Any, Mapping


class PluginIntegrationsAdapter:
    """Implements IntegrationsPort via existing modules."""

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
    ) -> str:
        from lib.adapters.integrations.model_router import pick_model_alias

        return pick_model_alias(
            msg,
            agent_name,
            dict(agent_cfg),
            primary_task_id=primary_task_id,
            config=dict(config) if config else None,
            data_dir=data_dir,
            routing_out=routing_out,
        )

    def resolve_ollama_settings(
        self,
        config: Mapping[str, Any] | None = None,
        data_dir: str = "",
    ) -> dict[str, Any]:
        from lib.adapters.integrations.ollama_routing import resolve_ollama_settings

        return resolve_ollama_settings(dict(config) if config else None, data_dir)

    def is_ollama_ready(self, **kwargs: Any) -> bool:
        from lib.adapters.integrations.ollama_routing import is_ollama_ready

        return bool(is_ollama_ready(**kwargs))

    def get_integration(self, name: str) -> Any:
        from lib.adapters.integrations.plugin_registry import get_integration

        return get_integration(name)

    def list_integrations(self) -> list[dict[str, str]]:
        from lib.adapters.integrations.plugin_registry import list_integrations

        return list_integrations()

    def agentmemory_url(self, *, mail_root: str | None = None) -> str:
        from lib.adapters.integrations.agentmemory_config import agentmemory_url

        return agentmemory_url(mail_root=mail_root)

    def is_no_llm_notice(self, msg: Any) -> bool:
        from lib.adapters.integrations.model_router import is_no_llm_notice

        return bool(is_no_llm_notice(msg))

    def tier_pro(self) -> str:
        from lib.adapters.integrations.model_router import TIER_PRO

        return TIER_PRO

    def tier_ollama(self) -> str:
        from lib.adapters.integrations.model_router import TIER_OLLAMA

        return TIER_OLLAMA

    def is_pro_allowed(self, agent_cfg: Mapping[str, Any]) -> bool:
        from lib.adapters.integrations.model_router import _pro_allowed

        return bool(_pro_allowed(dict(agent_cfg)))

    def post_json_with_wsl_fallback(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, Any] | None = None,
        *,
        timeout: int = 30,
    ) -> tuple[int, Any]:
        from lib.adapters.integrations.n8n.wsl_bridge import post_json_with_wsl_fallback

        return post_json_with_wsl_fallback(url, payload, headers, timeout=timeout)

    def invoke_tool(
        self,
        data_dir: str,
        *,
        agent_id: str,
        tool_id: str,
        inputs: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        from lib.adapters.integrations.external_tools import invoke_tool

        return invoke_tool(
            data_dir,
            agent_id=agent_id,
            tool_id=tool_id,
            inputs=inputs,
            dry_run=dry_run,
        )

    def archive_agentmemory(self, data_dir: str, agent_id: str) -> str:
        from lib.adapters.integrations.agentmemory_mount import archive_agentmemory

        return archive_agentmemory(data_dir, agent_id)

    def write_mcp_mount_hint(self, data_dir: str, agent_id: str) -> str:
        from lib.adapters.integrations.agentmemory_mount import write_mcp_mount_hint

        return write_mcp_mount_hint(data_dir, agent_id)

    def clear_mcp_mount_hint(self, data_dir: str, agent_id: str) -> None:
        from lib.adapters.integrations.agentmemory_mount import clear_mcp_mount_hint

        clear_mcp_mount_hint(data_dir, agent_id)


def build_integrations() -> PluginIntegrationsAdapter:
    return PluginIntegrationsAdapter()
