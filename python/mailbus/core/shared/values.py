"""跨上下文共用的枚举与值对象（权限、范围、语义标签）。"""

from __future__ import annotations

from enum import Enum


class Capability(str, Enum):
    """能力的唯一枚举源；契约中的 capabilities 必须与此一致。"""

    MESSAGE_SEND = "message_send"
    MESSAGE_READ = "message_read"
    TASK_CREATE = "task_create"
    TASK_DISPATCH = "task_dispatch"
    RESULT_SUBMIT = "result_submit"
    HITL_REQUEST = "hitl_request"
    HITL_RESOLVE = "hitl_resolve"
    WORKFLOW_CREATE = "workflow_create"
    WORKFLOW_MODIFY = "workflow_modify"
    EMPLOYEE_INVITE = "employee_invite"
    EMPLOYEE_REMOVE = "employee_remove"
    AGENT_DEREGISTER = "agent_deregister"
    LOG_READ = "log_read"
    SYSTEM_CONFIG = "system_config"
    ORG_MANAGE = "org_manage"
    CONSOLE_ADMIN = "console_admin"
    ALL = "*"


class DataScope(str, Enum):
    """数据可见范围：self 仅自己、team 含本团队、global 全量。"""

    SELF = "self"
    TEAM = "team"
    GLOBAL = "global"


class SemanticTag(str, Enum):
    """任务/节点状态的语义分类。

    自定义状态必须映射到其中一个标签，否则拒绝保存（见 workflow.rules）。
    """

    START = "start"
    ACTIVE = "active"
    BLOCKED = "blocked"
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"


class FileScope:
    """Agent 所在机器的工作区白名单。

    服务端只登记与下发，强制点在 Agent 侧；越权访问需走审批扩权。
    """

    __slots__ = ("paths",)

    def __init__(self, paths: tuple[str, ...] = ()) -> None:
        normalized = tuple(dict.fromkeys(p.strip() for p in paths if p and p.strip()))
        self.paths = normalized

    def covers(self, path: str) -> bool:
        return any(path == p or path.startswith(p.rstrip("/") + "/") for p in self.paths)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, FileScope) and other.paths == self.paths

    def __hash__(self) -> int:
        return hash(self.paths)
