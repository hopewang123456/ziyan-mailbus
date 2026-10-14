"""Fake OpsPort — no heartbeat / doctor / jobs side effects."""
from __future__ import annotations

from typing import Any, Mapping


class FakeOps:
    """Implements OpsPort for tests / dry-run."""

    def __init__(self) -> None:
        self.heartbeats: list[dict[str, Any]] = []
        self.alerts: list[dict[str, Any]] = []
        self.doctor_runs: int = 0
        self.jobs: list[str] = []
        self.clinic_runs: list[str] = []

    def heartbeat_scan(
        self,
        agents: Mapping[str, Any],
        agent_types: Mapping[str, Any],
        data_dir: str,
        **kwargs: Any,
    ) -> Any:
        self.heartbeats.append({"agents": dict(agents), "data_dir": data_dir, **kwargs})
        return {"ok": True, "fake": True}

    def push_alert(
        self,
        data_dir: str,
        alert_type: str,
        severity: str,
        agent: str = "",
        message: str = "",
        **kwargs: Any,
    ) -> Any:
        self.alerts.append(
            {
                "data_dir": data_dir,
                "alert_type": alert_type,
                "severity": severity,
                "agent": agent,
                "message": message,
                **kwargs,
            }
        )
        return {"ok": True}

    def run_doctor(self, *, mail_root: str | None = None, **kwargs: Any) -> dict[str, Any]:
        self.doctor_runs += 1
        return {"ok": True, "mail_root": mail_root, "checks": []}

    def scheduler_status(self) -> dict[str, Any]:
        return {"ok": True, "jobs": []}

    def run_job(self, job_id: str, data_dir: str, config: Mapping[str, Any] | None = None) -> int:
        del config
        self.jobs.append(job_id)
        return 0

    def list_clinic_tools(self) -> list[dict[str, Any]]:
        return []

    def run_clinic_tool(
        self,
        tool_id: str,
        *,
        params: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        self.clinic_runs.append(tool_id)
        return {"ok": True, "tool_id": tool_id, "params": dict(params or {})}

    def archive_all(
        self,
        data_dir: str,
        agents: Mapping[str, Any],
        archive_days: int = 3,
        max_messages: int = 300,
    ) -> dict[str, Any]:
        del agents, archive_days, max_messages
        return {"fake": data_dir}

    def is_online(self, data_dir: str, agent_name: str) -> bool:
        del data_dir, agent_name
        return True

    def load_status(self, data_dir: str) -> dict[str, Any]:
        return {"fake": True, "data_dir": data_dir}

    def scan_and_index(self, data_dir: str, agents: Mapping[str, Any]) -> Any:
        del agents
        return {"fake": True, "data_dir": data_dir}

    def search(
        self,
        data_dir: str,
        query_str: str = "",
        from_agent: str = "",
        **kwargs: Any,
    ) -> Any:
        del query_str, from_agent, kwargs
        return {"fake": True, "data_dir": data_dir}

    def load_alerts(self, data_dir: str) -> dict[str, Any]:
        return {"alerts": [], "fake": data_dir}

    def save_alerts(self, data_dir: str, alerts_data: Mapping[str, Any]) -> None:
        del data_dir, alerts_data

    def resolve_alert(self, data_dir: str, alert_id: str, reason: str = "manual") -> bool:
        del data_dir, alert_id, reason
        return True

    def check_api_keys(self, config: Mapping[str, Any]) -> list:
        del config
        return []

    def detect_api_stall(self, reply_text: str) -> str | None:
        del reply_text
        return None

    def api_stall_repush_wait_minutes(
        self,
        config: Mapping[str, Any] | None = None,
        data_dir: str = "",
    ) -> float:
        del config, data_dir
        return 5.0

    def read_reply_text_for_agent(
        self,
        data_dir: str,
        agent_name: str,
        msg_id: str = "",
    ) -> str:
        del data_dir, agent_name, msg_id
        return ""

    def append_inbox_task(
        self,
        data_dir: str,
        to: str,
        content: str,
        *,
        priority: str = "normal",
    ) -> None:
        del data_dir, to, content, priority
