"""Agent 台账的聚合与只读摘要。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Agent:
    """登记在册的 Agent 运行实体；不负责进程启停与运行时执行。"""

    agent_id: str
    name: str
    framework: str = ""
    model: str | None = None
    endpoint: str | None = None
    enabled: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    agent_type: str = "service"
    channel_type: str = "a2a"
    # token 只存密文与不可逆反查摘要，明文永不落库。
    endpoint_token: str | None = None
    endpoint_token_lookup_hash: str | None = None
    endpoint_token_prev: str | None = None
    endpoint_token_prev_lookup_hash: str | None = None
    endpoint_token_prev_expires_at: datetime | None = None
    last_seen_at: datetime | None = None
    pending_endpoint: str | None = None
    endpoint_review_status: str = "pending"
    endpoint_approved_by: str | None = None
    endpoint_approved_at: datetime | None = None
    deleted_at: datetime | None = None
    deleted_by: str | None = None


@dataclass(frozen=True, slots=True)
class AgentInvite:
    """一次性 Agent 注册邀请码；只保存摘要，明文仅创建响应返回一次。"""

    invite_id: str
    code_hash: str
    employee_name: str | None = None
    position_id: str | None = None
    capabilities: frozenset[str] = frozenset()
    permissions: frozenset[str] = frozenset()
    data_scope: str = "self"
    agent_type: str = "external"
    channel_type: str = "a2a"
    expires_at: datetime | None = None
    created_by: str | None = None
    created_at: datetime | None = None
    used_by_agent_id: str | None = None
    used_at: datetime | None = None
    revoked_at: datetime | None = None
    revoked_by: str | None = None

    @property
    def consumed(self) -> bool:
        return self.used_at is not None

    @property
    def revoked(self) -> bool:
        return self.revoked_at is not None


@dataclass(frozen=True, slots=True)
class AgentSummary:
    """跨上下文只读投影：布局与员工视图只需要名称与框架。"""

    agent_id: str
    name: str
    framework: str
