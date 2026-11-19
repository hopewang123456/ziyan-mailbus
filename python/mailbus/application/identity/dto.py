"""身份用例的输入/输出模型（application 内部 DTO）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mailbus.core.agents.models import AgentSummary
from mailbus.core.identity.models import Employee, Invite, Subject
from mailbus.core.identity.values import AccountType, EmployeeStatus
from mailbus.core.shared.values import Capability, DataScope, FileScope


@dataclass(frozen=True, slots=True)
class Actor:
    """会话解析后的调用者快照；api 只透传，不直接读字段。"""

    employee_id: str
    account_type: AccountType
    status: EmployeeStatus
    team_id: str | None = None
    capabilities: frozenset[Capability] = frozenset()
    data_scope: DataScope = DataScope.SELF
    file_scope: FileScope = FileScope()
    endpoint_approved: bool = False

    @classmethod
    def of(cls, employee: Employee) -> "Actor":
        return cls(
            employee_id=employee.employee_id,
            account_type=employee.account_type,
            status=employee.status,
            team_id=employee.team_id,
            capabilities=employee.capabilities,
            data_scope=employee.data_scope,
            file_scope=employee.file_scope,
            endpoint_approved=employee.endpoint_approved,
        )

    def to_subject(self) -> Subject:
        return Subject(
            employee_id=self.employee_id,
            account_type=self.account_type,
            status=self.status,
            team_id=self.team_id,
            capabilities=self.capabilities,
            data_scope=self.data_scope,
            file_scope=self.file_scope,
            endpoint_approved=self.endpoint_approved,
        )


@dataclass(frozen=True, slots=True)
class EmployeeView:
    """对外的员工视图：全部为可序列化的原始值。"""

    employee_id: str
    display_name: str
    account_type: str
    status: str
    team_id: str | None
    position_id: str | None
    seat_id: str | None
    agent_id: str | None
    agent_name: str | None
    agent_framework: str | None
    capabilities: tuple[str, ...]
    data_scope: str
    file_scope: tuple[str, ...]
    endpoint: str | None
    endpoint_approved: bool
    last_heartbeat: datetime | None

    @classmethod
    def of(
        cls, employee: Employee, agent: AgentSummary | None = None
    ) -> "EmployeeView":
        return cls(
            employee_id=employee.employee_id,
            display_name=employee.display_name,
            account_type=employee.account_type.value,
            status=employee.status.value,
            team_id=employee.team_id,
            position_id=employee.position_id,
            seat_id=employee.seat_id,
            agent_id=employee.agent_id,
            agent_name=agent.name if agent else None,
            agent_framework=agent.framework if agent else None,
            capabilities=tuple(sorted(cap.value for cap in employee.capabilities)),
            data_scope=employee.data_scope.value,
            file_scope=employee.file_scope.paths,
            endpoint=employee.endpoint,
            endpoint_approved=employee.endpoint_approved,
            last_heartbeat=employee.last_heartbeat,
        )


@dataclass(frozen=True, slots=True)
class InviteView:
    invite_code: str
    account_type: str
    team_id: str | None
    position_id: str | None
    data_scope: str
    capabilities: tuple[str, ...]
    expires_at: datetime | None

    @classmethod
    def of(cls, invite: Invite) -> "InviteView":
        return cls(
            invite_code=invite.invite_code,
            account_type=invite.account_type.value,
            team_id=invite.team_id,
            position_id=invite.position_id,
            data_scope=invite.data_scope.value,
            capabilities=tuple(sorted(cap.value for cap in invite.capabilities)),
            expires_at=invite.expires_at,
        )


@dataclass(frozen=True, slots=True)
class SessionResult:
    employee: EmployeeView
    token: str


@dataclass(frozen=True, slots=True)
class ApplyResult:
    employee: EmployeeView
    token: str | None


@dataclass(frozen=True, slots=True)
class BootstrapStepView:
    step: str
    done: bool
    skippable: bool


@dataclass(frozen=True, slots=True)
class BootstrapStatusView:
    steps: tuple[BootstrapStepView, ...]
    completed: bool


@dataclass(frozen=True, slots=True)
class ApplyCommand:
    display_name: str
    account_type: AccountType
    invite_code: str | None = None
    endpoint: str | None = None
    seat_id: str | None = None
    agent_id: str | None = None


@dataclass(frozen=True, slots=True)
class ReviewCommand:
    approved: bool
    note: str | None = None


@dataclass(frozen=True, slots=True)
class InviteCommand:
    account_type: AccountType
    team_id: str | None = None
    position_id: str | None = None
    capabilities: tuple[Capability, ...] = ()
    data_scope: DataScope = DataScope.SELF
    expires_in_hours: int = 72


@dataclass(frozen=True, slots=True)
class SuperAdminCommand:
    display_name: str
    employee_id: str | None = None


@dataclass(frozen=True, slots=True)
class ModelConfigCommand:
    provider: str
    model: str
    api_base: str | None = None


@dataclass(frozen=True, slots=True)
class OccupantView:
    """布局只读投影需要的最小员工信息（跨上下文只传值，不传实体）。"""

    employee_id: str
    display_name: str
    team_id: str | None
    position_id: str | None
    seat_id: str | None
    agent_id: str | None
    status: str
    last_heartbeat: datetime | None


def employee_view(
    employee: Employee, agent: AgentSummary | None = None
) -> EmployeeView:
    return EmployeeView.of(employee, agent)


def invite_view(invite: Invite) -> InviteView:
    return InviteView.of(invite)


def make_apply_command(
    display_name: str,
    account_type: str,
    invite_code: str | None = None,
    endpoint: str | None = None,
    seat_id: str | None = None,
    agent_id: str | None = None,
) -> ApplyCommand:
    return ApplyCommand(
        display_name=display_name,
        account_type=AccountType(account_type),
        invite_code=invite_code,
        endpoint=endpoint,
        seat_id=seat_id,
        agent_id=agent_id,
    )


def make_review_command(approved: bool, note: str | None = None) -> ReviewCommand:
    return ReviewCommand(approved=approved, note=note)


def make_invite_command(
    account_type: str,
    team_id: str | None = None,
    position_id: str | None = None,
    capabilities: tuple[Capability, ...] = (),
    data_scope: str = "self",
    expires_in_hours: int = 72,
) -> InviteCommand:
    return InviteCommand(
        account_type=AccountType(account_type),
        team_id=team_id,
        position_id=position_id,
        capabilities=capabilities,
        data_scope=DataScope(data_scope),
        expires_in_hours=expires_in_hours,
    )


def make_super_admin_command(
    display_name: str, employee_id: str | None = None
) -> SuperAdminCommand:
    return SuperAdminCommand(display_name=display_name, employee_id=employee_id)


def make_model_config_command(
    provider: str, model: str, api_base: str | None = None
) -> ModelConfigCommand:
    return ModelConfigCommand(provider=provider, model=model, api_base=api_base)
