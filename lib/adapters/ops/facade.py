"""OpsPort facade — delegates to root ops modules until full move."""
from __future__ import annotations

from typing import Any, Mapping


class RootOpsAdapter:
    """Implements OpsPort by calling existing lib.* ops modules."""

    def heartbeat_scan(
        self,
        agents: Mapping[str, Any],
        agent_types: Mapping[str, Any],
        data_dir: str,
        **kwargs: Any,
    ) -> Any:
        from lib.adapters.ops.heartbeat import heartbeat_scan

        return heartbeat_scan(agents, agent_types, data_dir, **kwargs)

    def push_alert(
        self,
        data_dir: str,
        alert_type: str,
        severity: str,
        agent: str = "",
        message: str = "",
        **kwargs: Any,
    ) -> Any:
        from lib.adapters.ops.alerter import push_alert

        return push_alert(data_dir, alert_type, severity, agent, message, **kwargs)

    def run_doctor(self, *, mail_root: str | None = None, **kwargs: Any) -> dict[str, Any]:
        from pathlib import Path

        from lib.adapters.ops.doctor_checks import run_doctor_checks

        root = Path(mail_root) if mail_root else None
        return run_doctor_checks(mail_root=root, **kwargs)

    def scheduler_status(self) -> dict[str, Any]:
        from lib.adapters.ops.scheduler import get_scheduler_status

        return get_scheduler_status()

    def run_job(self, job_id: str, data_dir: str, config: Mapping[str, Any] | None = None) -> int:
        from lib.adapters.ops import jobs

        cfg = dict(config or {})
        runners = {
            "scan": lambda: jobs.run_scan(data_dir, cfg),
            "memory_bridge": lambda: jobs.run_memory_bridge(data_dir),
            "agentmemory_watchdog": lambda: jobs.run_agentmemory_watchdog(data_dir),
            "log_rotate": lambda: jobs.run_log_rotate(data_dir),
            "patrol": lambda: jobs.run_patrol(data_dir),
            "pipeline_watchdog": lambda: jobs.run_pipeline_watchdog(data_dir),
            "platform_scout": lambda: jobs.run_platform_scout(data_dir),
            "pipeline_repair": lambda: jobs.run_pipeline_repair(data_dir),
            "intake_bridge": lambda: jobs.run_intake_bridge(data_dir),
            "triage_inbox": lambda: jobs.run_triage_inbox(data_dir, cfg),
            "daily_report": lambda: jobs.run_daily_report(data_dir),
        }
        fn = runners.get(job_id)
        if fn is None:
            return 1
        return int(fn())

    def list_clinic_tools(self) -> list[dict[str, Any]]:
        from lib.adapters.ops.clinic_tools import list_clinic_tools

        return list_clinic_tools()

    def run_clinic_tool(
        self,
        tool_id: str,
        *,
        params: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        from lib.adapters.ops.clinic_tools import run_clinic_tool

        return run_clinic_tool(tool_id, params=dict(params or {}), **kwargs)

    def archive_all(
        self,
        data_dir: str,
        agents: Mapping[str, Any],
        archive_days: int = 3,
        max_messages: int = 300,
    ) -> dict[str, Any]:
        from lib.adapters.ops.archiver import archive_all

        return archive_all(data_dir, dict(agents), archive_days, max_messages)

    def is_online(self, data_dir: str, agent_name: str) -> bool:
        from lib.adapters.ops.heartbeat import is_online

        return bool(is_online(data_dir, agent_name))

    def load_status(self, data_dir: str) -> dict[str, Any]:
        from lib.adapters.ops.heartbeat import load_status

        return load_status(data_dir)

    def scan_and_index(self, data_dir: str, agents: Mapping[str, Any]) -> Any:
        from lib.adapters.ops.search import scan_and_index

        return scan_and_index(data_dir, dict(agents))

    def search(
        self,
        data_dir: str,
        query_str: str = "",
        from_agent: str = "",
        **kwargs: Any,
    ) -> Any:
        from lib.adapters.ops.search import search

        return search(data_dir, query_str, from_agent, **kwargs)

    def load_alerts(self, data_dir: str) -> dict[str, Any]:
        from lib.adapters.ops.alerter import load_alerts

        return load_alerts(data_dir)

    def save_alerts(self, data_dir: str, alerts_data: Mapping[str, Any]) -> None:
        from lib.adapters.ops.alerter import save_alerts

        save_alerts(data_dir, dict(alerts_data))

    def resolve_alert(self, data_dir: str, alert_id: str, reason: str = "manual") -> bool:
        from lib.adapters.ops.alerter import resolve_alert

        return bool(resolve_alert(data_dir, alert_id, reason))

    def check_api_keys(self, config: Mapping[str, Any]) -> list:
        from lib.adapters.ops.heartbeat import check_api_keys

        return check_api_keys(dict(config))

    def detect_api_stall(self, reply_text: str) -> str | None:
        from lib.adapters.ops.api_stall_detect import detect_api_stall

        return detect_api_stall(reply_text)

    def api_stall_repush_wait_minutes(
        self,
        config: Mapping[str, Any] | None = None,
        data_dir: str = "",
    ) -> float:
        from lib.adapters.ops.api_stall_detect import api_stall_repush_wait_minutes

        return float(api_stall_repush_wait_minutes(dict(config) if config else None, data_dir))

    def read_reply_text_for_agent(
        self,
        data_dir: str,
        agent_name: str,
        msg_id: str = "",
    ) -> str:
        from lib.adapters.ops.api_stall_detect import read_reply_text_for_agent

        return read_reply_text_for_agent(data_dir, agent_name, msg_id)

    def append_inbox_task(
        self,
        data_dir: str,
        to: str,
        content: str,
        *,
        priority: str = "normal",
    ) -> None:
        from lib.adapters.ops.jobs import _append_inbox_task

        _append_inbox_task(data_dir, to, content, priority=priority)


def build_ops() -> RootOpsAdapter:
    return RootOpsAdapter()
