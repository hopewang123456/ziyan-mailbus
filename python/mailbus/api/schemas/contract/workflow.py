"""工作流域契约模型：定义、版本、Graph 与校验结果。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from mailbus.api.schemas.contract.common import Page

NodeType = Literal[
    "start",
    "agent",
    "human",
    "condition",
    "parallel_join",
    "final_approval",
]


class WorkflowOut(BaseModel):
    workflow_id: str
    name: str
    latest_version: int
    published_version: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WorkflowListOut(Page[WorkflowOut]):
    pass


class VersionOut(BaseModel):
    workflow_id: str
    version: int
    state: str
    revision: int
    created_at: datetime | None = None
    published_at: datetime | None = None


class VersionListOut(Page[VersionOut]):
    pass


class GraphNodeIn(BaseModel):
    node_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    node_type: NodeType
    position_id: str | None = None
    seq: int = Field(default=0, ge=0)
    prompt_template: str | None = None
    needs_artifacts_from: list[str] = Field(default_factory=list)
    max_retries: int = Field(default=3, ge=0)
    max_loops: int = Field(default=3, ge=0)
    timeout_seconds: int | None = Field(default=None, ge=0)
    config: dict[str, Any] | None = None
    pos_x: float = 0
    pos_y: float = 0


class GraphEdgeIn(BaseModel):
    from_node_id: str = Field(min_length=1, max_length=64)
    to_node_id: str = Field(min_length=1, max_length=64)
    condition: str | None = None


class WorkflowGraphIn(BaseModel):
    nodes: list[GraphNodeIn] = Field(default_factory=list)
    edges: list[GraphEdgeIn] = Field(default_factory=list)


class WorkflowIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    graph: WorkflowGraphIn | None = None


class GraphIn(BaseModel):
    graph: WorkflowGraphIn
    revision: int = Field(ge=1)


class GraphOut(BaseModel):
    graph: WorkflowGraphIn
    revision: int


class EdgeRefOut(BaseModel):
    from_node_id: str
    to_node_id: str


class ValidateIssueOut(BaseModel):
    code: str
    message_zh: str
    node_id: str | None = None
    edge: EdgeRefOut | None = None


class ValidateOut(BaseModel):
    ok: bool
    errors: list[ValidateIssueOut] = Field(default_factory=list)
    warnings: list[ValidateIssueOut] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)
