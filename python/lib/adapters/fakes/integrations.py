"""Fake IntegrationsPort — no model router / ollama / plugins."""
from __future__ import annotations

from typing import Any, Mapping


class FakeIntegrations:
    """Implements IntegrationsPort for tests / dry-run."""

    def __init__(self, *, model_alias: str = "fake-model", ollama_ready: bool = True) -> None:
        self.model_alias = model_alias
        self.ollama_ready = ollama_ready
        self.picks: list[str] = []
        self._integrations: dict[str, Any] = {}

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
        del msg, agent_cfg, primary_task_id, config, data_dir, routing_out
        self.picks.append(agent_name)
        return self.model_alias

    def resolve_ollama_settings(
        self,
        config: Mapping[str, Any] | None = None,
        data_dir: str = "",
    ) -> dict[str, Any]:
        del config, data_dir
        return {"base_url": "http://127.0.0.1:11434", "model": self.model_alias}

    def is_ollama_ready(self, **kwargs: Any) -> bool:
        del kwargs
        return self.ollama_ready

    def get_integration(self, name: str) -> Any:
        return self._integrations.get(name)

    def list_integrations(self) -> list[dict[str, str]]:
        return [{"name": k, "kind": "fake"} for k in self._integrations]

    def agentmemory_url(self, *, mail_root: str | None = None) -> str:
        del mail_root
        return "http://127.0.0.1:0/fake-agentmemory"

    def is_no_llm_notice(self, msg: Any) -> bool:
        del msg
        return False

    def tier_pro(self) -> str:
        return "deepseek-pro"

    def tier_ollama(self) -> str:
        return "ollama-local"

    def is_pro_allowed(self, agent_cfg: Mapping[str, Any]) -> bool:
        del agent_cfg
        return False

    def post_json_with_wsl_fallback(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, Any] | None = None,
        *,
        timeout: int = 30,
    ) -> tuple[int, Any]:
        del url, payload, headers, timeout
        return 200, {"ok": True, "fake": True}

    def invoke_tool(
        self,
        data_dir: str,
        *,
        agent_id: str,
        tool_id: str,
        inputs: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        del data_dir, agent_id, tool_id, inputs, dry_run
        return {"ok": True, "fake": True}

    def archive_agentmemory(self, data_dir: str, agent_id: str) -> str:
        del data_dir, agent_id
        return ""

    def write_mcp_mount_hint(self, data_dir: str, agent_id: str) -> str:
        del data_dir, agent_id
        return ""

    def clear_mcp_mount_hint(self, data_dir: str, agent_id: str) -> None:
        del data_dir, agent_id
