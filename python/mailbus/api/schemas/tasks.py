"""task 分组的对外模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# 列表过滤参数的白名单：非法状态由 FastAPI 直接返回 422，而不是落成领域 409。
TaskStateFilter = Literal[
    "draft", "queued", "running", "blocked", "done", "failed", "cancelled"
]


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=64)
    owner_id: str | None = None
    workflow_id: str | None = None
    workflow_version: int | None = None


class TaskNodeOut(BaseModel):
    node_id: str
    name: str
    order: int
    state: str


class TaskOut(BaseModel):
    task_id: str
    title: str
    state: str
    workflow_id: str | None = None
    workflow_version: int | None = None
    owner_id: str | None = None
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    nodes: list[TaskNodeOut]


class PublicTaskNodeOut(BaseModel):
    """公开任务节点投影：只暴露展示所需的名称、顺序与状态。"""

    name: str
    order: int
    state: str


class PublicTaskOut(BaseModel):
    """公开协同任务投影：不暴露创建者、负责人、流程标识与内部节点 ID。"""

    task_id: str
    title: str
    state: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    nodes: list[PublicTaskNodeOut]
