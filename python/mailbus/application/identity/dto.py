"""身份用例的输入/输出模型（application 内部 DTO）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mailbus.core.agents.models import AgentSummary
from mailbus.core.identity.models import Employee, Subject
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
    permissions: tuple[str, ...]
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
            permissions=tuple(sorted(cap.value for cap in employee.capabilities)),
            data_scope=employee.data_scope.value,
            file_scope=employee.file_scope.paths,
            endpoint=employee.endpoint,
            endpoint_approved=employee.endpoint_approved,
            last_heartbeat=employee.last_heartbeat,
        )


@dataclass(frozen=True, slots=True)
class SessionResult:
    employee: EmployeeView
    token: str


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


def make_super_admin_command(
    display_name: str, employee_id: str | None = None
) -> SuperAdminCommand:
    return SuperAdminCommand(display_name=display_name, employee_id=employee_id)


def make_model_config_command(
    provider: str, model: str, api_base: str | None = None
) -> ModelConfigCommand:
    return ModelConfigCommand(provider=provider, model=model, api_base=api_base)
