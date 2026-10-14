"""Orchestration adapters."""
from __future__ import annotations

from lib.adapters.orchestration.audit import FileAuditAdapter, NoopAudit
from lib.adapters.orchestration.budget import FileBudgetMeter
from lib.adapters.orchestration.fsm import TaskFsmAdapter
from lib.adapters.orchestration.human_gate import HumanGateAdapter
from lib.adapters.orchestration.notifier import FileNotifier
from lib.domain.errors import PAUSE_REASON_BUDGET
from lib.interfaces.gates import AuditPort, HumanGatePort
from lib.interfaces.orchestration import BudgetMeterPort, NotifierPort, TaskFsmPort


def build_task_fsm() -> TaskFsmPort:
    return TaskFsmAdapter()


def build_budget_meter(data_dir: str) -> BudgetMeterPort:
    return FileBudgetMeter(data_dir)


def build_notifier(data_dir: str) -> NotifierPort:
    return FileNotifier(data_dir)


def build_human_gate(
    data_dir: str,
    *,
    audit: AuditPort | None = None,
) -> HumanGatePort:
    return HumanGateAdapter(data_dir, audit=audit)


def build_audit(data_dir: str, *, file_sink: bool = True) -> AuditPort:
    return FileAuditAdapter(data_dir) if file_sink else NoopAudit()


__all__ = [
    "FileAuditAdapter",
    "FileBudgetMeter",
    "FileNotifier",
    "HumanGateAdapter",
    "NoopAudit",
    "PAUSE_REASON_BUDGET",
    "TaskFsmAdapter",
    "build_audit",
    "build_budget_meter",
    "build_human_gate",
    "build_notifier",
    "build_task_fsm",
]
