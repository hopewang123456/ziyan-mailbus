"""身份上下文的枚举与常量。

状态与能力枚举只允许定义在 core（守卫 G7）。
"""

from __future__ import annotations

from enum import Enum

from mailbus.core.shared.values import Capability


class AccountType(str, Enum):
    """账号类型：真人与 Agent 同表，用类型区分。"""

    HUMAN = "human"
    AGENT = "agent"


class EmployeeStatus(str, Enum):
    """员工生命周期状态。

    pending（已申请待审核）→ active（已激活）↔ offline（心跳超时）
    → deregistered（注销，终态）。
    """

    PENDING = "pending"
    ACTIVE = "active"
    OFFLINE = "offline"
    DEREGISTERED = "deregistered"


# 在勤即可用状态：offline 只是心跳超时（离席），可被心跳恢复，不等于停权。
# 权限判定、员工列表筛选、出站投递统一以此为口径（守卫 G7：状态口径只在 core 定义）。
ON_DUTY_STATUSES: frozenset[EmployeeStatus] = frozenset(
    {EmployeeStatus.ACTIVE, EmployeeStatus.OFFLINE}
)


class BootstrapStep(str, Enum):
    """首次部署三步向导。"""

    SUPER_ADMIN = "super_admin"
    MODEL_CONFIG = "model_config"
    FIRST_TEAM = "first_team"


BOOTSTRAP_STEPS: tuple[BootstrapStep, ...] = (
    BootstrapStep.SUPER_ADMIN,
    BootstrapStep.MODEL_CONFIG,
    BootstrapStep.FIRST_TEAM,
)

SKIPPABLE_STEPS: frozenset[BootstrapStep] = frozenset(
    {BootstrapStep.MODEL_CONFIG, BootstrapStep.FIRST_TEAM}
)

# 「管理者」由超管在员工页指定；启用时并入这组能力，停用时只移除 CONSOLE_ADMIN。
# 不含 SYSTEM_CONFIG（系统配置）与 EMPLOYEE_REMOVE / AGENT_DEREGISTER（注销）。
MANAGER_CAPABILITIES: frozenset[Capability] = frozenset(
    {
        Capability.CONSOLE_ADMIN,
        Capability.EMPLOYEE_INVITE,
        Capability.ORG_MANAGE,
        Capability.HITL_REQUEST,
        Capability.HITL_RESOLVE,
        Capability.TASK_CREATE,
        Capability.TASK_DISPATCH,
        Capability.WORKFLOW_CREATE,
        Capability.WORKFLOW_MODIFY,
        Capability.MESSAGE_SEND,
        Capability.LOG_READ,
    }
)
