"""身份上下文的聚合与只读模型。

Employee 是唯一写聚合：冻结 dataclass，状态变更只能由 rules 生成新实例。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mailbus.core.identity.values import AccountType, EmployeeStatus
from mailbus.core.shared.values import Capability, DataScope, FileScope


@dataclass(frozen=True, slots=True)
class Employee:
    """员工聚合根（真人与 Agent 同构）。"""

    employee_id: str
    display_name: str
    account_type: AccountType
    status: EmployeeStatus
    team_id: str | None = None
    position_id: str | None = None
    seat_id: str | None = None
    capabilities: frozenset[Capability] = frozenset()
    data_scope: DataScope = DataScope.SELF
    file_scope: FileScope = FileScope()
    endpoint: str | None = None
    endpoint_approved: bool = False
    approved_at: datetime | None = None
    last_heartbeat: datetime | None = None
    agent_id: str | None = None


@dataclass(frozen=True, slots=True)
class Registration:
    """创建员工所需的最小输入；approved=True 表示邀请已预先核准。"""

    employee_id: str
    display_name: str
    account_type: AccountType
    team_id: str | None = None
    position_id: str | None = None
    seat_id: str | None = None
    capabilities: frozenset[Capability] = frozenset()
    data_scope: DataScope = DataScope.SELF
    file_scope: FileScope = FileScope()
    endpoint: str | None = None
    approved: bool = False
    agent_id: str | None = None


@dataclass(frozen=True, slots=True)
class Subject:
    """权限判定的输入：只包含判定需要的字段。"""

    employee_id: str
    account_type: AccountType
    status: EmployeeStatus
    team_id: str | None = None
    capabilities: frozenset[Capability] = frozenset()
    data_scope: DataScope = DataScope.SELF
    file_scope: FileScope = FileScope()
    endpoint_approved: bool = False


def subject_of(employee: Employee) -> Subject:
    return Subject(
        employee_id=employee.employee_id,
        account_type=employee.account_type,
        status=employee.status,
        team_id=employee.team_id,
        capabilities=employee.capabilities,
        data_scope=employee.data_scope,
        file_scope=employee.file_scope,
        endpoint_approved=employee.endpoint_approved,
    )


@dataclass(frozen=True, slots=True)
class Invite:
    """一次性邀请码：携带预授予的能力与范围。"""

    invite_code: str
    account_type: AccountType
    team_id: str | None = None
    position_id: str | None = None
    data_scope: DataScope = DataScope.SELF
    capabilities: frozenset[Capability] = frozenset()
    created_by: str | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None
    consumed_by: str | None = None
    consumed_at: datetime | None = None

    @property
    def consumed(self) -> bool:
        return self.consumed_at is not None
