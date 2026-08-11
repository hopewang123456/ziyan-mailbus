"""Ops port — heartbeat / alerter / doctor / scheduler / jobs / clinic."""
from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class OpsPort(Protocol):
    """Minimal ops surface used by application / composition.

    Concrete wiring may delegate to root modules (``lib.heartbeat``,
    ``lib.alerter``, …) until they fully land under ``adapters.ops``.
    """

    def heartbeat_scan(
        self,
        agents: Mapping[str, Any],
        agent_types: Mapping[str, Any],
        data_dir: str,
        **kwargs: Any,
    ) -> Any: ...

    def push_alert(
        self,
        data_dir: str,
        alert_type: str,
        severity: str,
        agent: str = "",
        message: str = "",
        **kwargs: Any,
    ) -> Any: ...

    def run_doctor(self, *, mail_root: str | None = None, **kwargs: Any) -> dict[str, Any]: ...

    def scheduler_status(self) -> dict[str, Any]: ...

    def run_job(self, job_id: str, data_dir: str, config: Mapping[str, Any] | None = None) -> int: ...

    def list_clinic_tools(self) -> list[dict[str, Any]]: ...

    def run_clinic_tool(
        self,
        tool_id: str,
        *,
        params: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any: ...

    def archive_all(
        self,
        data_dir: str,
        agents: Mapping[str, Any],
        archive_days: int = 3,
        max_messages: int = 300,
    ) -> dict[str, Any]: ...

    def is_online(self, data_dir: str, agent_name: str) -> bool: ...

    def load_status(self, data_dir: str) -> dict[str, Any]: ...

    def scan_and_index(self, data_dir: str, agents: Mapping[str, Any]) -> Any: ...

    def search(
        self,
        data_dir: str,
        query_str: str = "",
        from_agent: str = "",
        **kwargs: Any,
    ) -> Any: ...

    def load_alerts(self, data_dir: str) -> dict[str, Any]: ...

    def save_alerts(self, data_dir: str, alerts_data: Mapping[str, Any]) -> None: ...

    def resolve_alert(self, data_dir: str, alert_id: str, reason: str = "manual") -> bool: ...

    def check_api_keys(self, config: Mapping[str, Any]) -> list: ...

    def detect_api_stall(self, reply_text: str) -> str | None: ...

    def api_stall_repush_wait_minutes(
        self,
        config: Mapping[str, Any] | None = None,
        data_dir: str = "",
    ) -> float: ...

    def read_reply_text_for_agent(
        self,
        data_dir: str,
        agent_name: str,
        msg_id: str = "",
    ) -> str: ...

    def append_inbox_task(
        self,
        data_dir: str,
        to: str,
        content: str,
        *,
        priority: str = "normal",
    ) -> None: ...
