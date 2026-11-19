"""审计与告警只读投影：审核统计取自审批记录，告警取自指标规则。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from mailbus.application.metrics.dto import AlertView
from mailbus.application.metrics.service import MetricsService
from mailbus.application.queries.ports import ReadUnitOfWork
from mailbus.core.approval.values import ApprovalStatus

_AUDITED = frozenset(
    {
        ApprovalStatus.APPROVED,
        ApprovalStatus.REJECTED,
        ApprovalStatus.EXPIRED,
        ApprovalStatus.ACKNOWLEDGED,
    }
)
_PASS = frozenset({ApprovalStatus.APPROVED, ApprovalStatus.ACKNOWLEDGED})


@dataclass(frozen=True, slots=True)
class ReviewerStat:
    pass_count: int
    fail_count: int
    warn_count: int
    total: int


@dataclass(frozen=True, slots=True)
class AuditStatsView:
    total_tasks: int
    audited_tasks: int
    pending_audit_tasks: int
    pass_count: int
    fail_count: int
    warn_count: int
    by_reviewer: dict[str, ReviewerStat]


class AuditQuery:
    def __init__(
        self,
        uow_factory: Callable[[], ReadUnitOfWork],
        metrics: MetricsService,
    ) -> None:
        self._uow = uow_factory
        self._metrics = metrics

    def stats(self) -> AuditStatsView:
        with self._uow() as uow:
            tasks = uow.tasks.list_all()
            approvals = uow.approvals.list_all()
        audited = [item for item in approvals if item.status in _AUDITED]
        pending = [item for item in approvals if item.status is ApprovalStatus.PENDING]
        return AuditStatsView(
            total_tasks=len(tasks),
            audited_tasks=len({item.task_id for item in audited}),
            pending_audit_tasks=len({item.task_id for item in pending}),
            pass_count=sum(1 for item in audited if item.status in _PASS),
            fail_count=sum(
                1 for item in audited if item.status is ApprovalStatus.REJECTED
            ),
            warn_count=sum(
                1 for item in audited if item.status is ApprovalStatus.EXPIRED
            ),
            by_reviewer=_reviewers(audited),
        )

    def alerts(self) -> tuple[AlertView, ...]:
        return self._metrics.alerts()


def _reviewers(approvals: list) -> dict[str, ReviewerStat]:
    grouped: dict[str, dict[str, int]] = {}
    for item in approvals:
        reviewer = item.resolved_by
        if not reviewer:
            continue
        bucket = grouped.setdefault(
            reviewer, {"pass": 0, "fail": 0, "warn": 0}
        )
        if item.status in _PASS:
            bucket["pass"] += 1
        elif item.status is ApprovalStatus.REJECTED:
            bucket["fail"] += 1
        else:
            bucket["warn"] += 1
    result = {
        reviewer: ReviewerStat(
            pass_count=value["pass"],
            fail_count=value["fail"],
            warn_count=value["warn"],
            total=value["pass"] + value["fail"] + value["warn"],
        )
        for reviewer, value in grouped.items()
    }
    return dict(sorted(result.items(), key=lambda pair: -pair[1].total))
