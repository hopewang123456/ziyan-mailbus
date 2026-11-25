"""Agent 用例的输入/输出模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mailbus.core.agents.models import Agent, AgentInvite


@dataclass(frozen=True, slots=True)
class AgentCommand:
    name: str
    framework: str = ""
    model: str | None = None
    endpoint: str | None = None
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class AgentUpdateCommand:
    """只携带客户端显式提交的字段（PATCH 语义）。"""

    changes: dict[str, object]


@dataclass(frozen=True, slots=True)
class AgentView:
    agent_id: str
    name: str
    framework: str
    model: str | None
    endpoint: str | None
    enabled: bool
    created_at: datetime | None
    updated_at: datetime | None

    @classmethod
    def of(cls, agent: Agent) -> "AgentView":
        return cls(
            agent_id=agent.agent_id,
            name=agent.name,
            framework=agent.framework,
            model=agent.model,
            endpoint=agent.endpoint,
            enabled=agent.enabled,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )


def agent_view(agent: Agent) -> AgentView:
    return AgentView.of(agent)


@dataclass(frozen=True, slots=True)
class AgentAdminView:
    agent_id: str
    name: str
    framework: str
    model: str | None
    endpoint: str | None
    pending_endpoint: str | None
    endpoint_review_status: str
    enabled: bool
    agent_type: str
    channel_type: str
    online: bool
    last_seen_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None

    @classmethod
    def of(cls, agent: Agent, *, online: bool) -> "AgentAdminView":
        return cls(
            agent_id=agent.agent_id,
            name=agent.name,
            framework=agent.framework,
            model=agent.model,
            endpoint=agent.endpoint,
            pending_endpoint=agent.pending_endpoint,
            endpoint_review_status=agent.endpoint_review_status,
            enabled=agent.enabled,
            agent_type=agent.agent_type,
            channel_type=agent.channel_type,
            online=online,
            last_seen_at=agent.last_seen_at,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )


@dataclass(frozen=True, slots=True)
class AgentRegisterCommand:
    invite_code: str
    name: str
    framework: str = ""
    model: str | None = None
    endpoint: str | None = None
    agent_type: str = "external"
    channel_type: str = "a2a"


@dataclass(frozen=True, slots=True)
class AgentRegistration:
    agent_id: str
    employee_id: str
    token: str
    endpoint: str | None
    endpoint_review_status: str


@dataclass(frozen=True, slots=True)
class AgentTokenResult:
    agent_id: str
    token: str
    fingerprint: str
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AgentInviteCommand:
    employee_name: str | None = None
    position_id: str | None = None
    capabilities: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    data_scope: str = "self"
    agent_type: str = "external"
    channel_type: str = "a2a"
    expires_in_hours: int | None = None


@dataclass(frozen=True, slots=True)
class AgentInviteView:
    invite_id: str
    invite_code: str | None
    employee_name: str | None
    position_id: str | None
    capabilities: tuple[str, ...]
    permissions: tuple[str, ...]
    data_scope: str
    agent_type: str
    channel_type: str
    created_by: str | None
    created_at: datetime | None
    expires_at: datetime | None
    used_by_agent_id: str | None
    used_at: datetime | None
    revoked_at: datetime | None

    @classmethod
    def of(cls, invite: AgentInvite, code: str | None = None) -> "AgentInviteView":
        return cls(
            invite_id=invite.invite_id,
            invite_code=code,
            employee_name=invite.employee_name,
            position_id=invite.position_id,
            capabilities=tuple(sorted(invite.capabilities)),
            permissions=tuple(sorted(invite.permissions)),
            data_scope=invite.data_scope,
            agent_type=invite.agent_type,
            channel_type=invite.channel_type,
            created_by=invite.created_by,
            created_at=invite.created_at,
            expires_at=invite.expires_at,
            used_by_agent_id=invite.used_by_agent_id,
            used_at=invite.used_at,
            revoked_at=invite.revoked_at,
        )


def make_agent_command(
    name: str,
    framework: str = "",
    model: str | None = None,
    endpoint: str | None = None,
    enabled: bool = True,
) -> AgentCommand:
    return AgentCommand(
        name=name,
        framework=framework,
        model=model,
        endpoint=endpoint,
        enabled=enabled,
    )


def make_agent_update_command(changes: dict[str, object]) -> AgentUpdateCommand:
    return AgentUpdateCommand(changes=dict(changes))
