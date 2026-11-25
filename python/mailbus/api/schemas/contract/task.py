"""任务域契约模型：列表/详情/run/认领/结果/取消/重跑/审批/追迹。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from mailbus.api.schemas.approval import ApprovalOut
from mailbus.api.schemas.contract.common import Page

TaskState = Literal["pending", "running", "blocked", "done", "cancelled", "failed"]
RunState = Literal["pending", "running", "done", "failed", "cancelled", "skipped"]


class TaskSummaryOut(BaseModel):
    task_id: str
    title: str
    state: str
    owner_id: str | None = None
    workflow_id: str | None = None
    workflow_version: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    current_node: str | None = None
    progress_done: int = 0
    progress_total: int = 0
    claimable: bool = False


class TaskListOut(Page[TaskSummaryOut]):
    pass


class TaskRunOut(BaseModel):
    run_id: str
    node_id: str
    attempt_no: int
    fanout_slot: int = 0
    state: str
    assigned_employee_id: str | None = None
    fanout_group: str | None = None
    dispatched_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: str | None = None


class TaskNodeOut(BaseModel):
    node_id: str
    name: str
    seq: int
    state: str
    current_run_id: str | None = None
    runs: list[TaskRunOut] = Field(default_factory=list)


class ArtifactOut(BaseModel):
    artifact_id: str
    task_id: str
    node_id: str | None = None
    run_id: str | None = None
    file_name: str
    artifact_type: str | None = None
    description: str | None = None
    size_bytes: int | None = None
    created_by: str | None = None
    created_at: datetime | None = None


class TaskDetailOut(BaseModel):
    task_id: str
    title: str
    state: str
    owner_id: str | None = None
    created_by: str | None = None
    workflow_id: str | None = None
    workflow_version: int | None = None
    termination_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    nodes: list[TaskNodeOut] = Field(default_factory=list)
    runs: list[TaskRunOut] = Field(default_factory=list)
    artifacts: list[ArtifactOut] = Field(default_factory=list)


class TaskCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=64)
    workflow_id: str | None = None
    owner_id: str | None = None
    variables: dict[str, str] = Field(default_factory=dict)


class TaskCountersOut(BaseModel):
    """导航角标：由 run 与 approval 聚合，不落任务表。"""

    claimable: int = 0
    mine_open: int = 0
    approvals: int = 0


class ResultIn(BaseModel):
    attempt_no: int = Field(ge=1)
    result: str = Field(min_length=1)
    artifact_ids: list[str] = Field(default_factory=list)


class CancelIn(BaseModel):
    reason: str = Field(default="manual", min_length=1, max_length=64)


class RerunJoinIn(BaseModel):
    fanout_group: str = Field(min_length=1, max_length=64)
    scope: Literal["join", "downstream"] = "join"


class ApprovalListOut(Page[ApprovalOut]):
    pass


class ResolveIn(BaseModel):
    decision: Literal["approved", "rejected"]
    comment: str | None = None


class TaskTraceEventOut(BaseModel):
    at: datetime | None = None
    kind: str
    node_id: str | None = None
    run_id: str | None = None
    attempt_no: int | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class TaskTraceOut(BaseModel):
    task_id: str
    events: list[TaskTraceEventOut] = Field(default_factory=list)
