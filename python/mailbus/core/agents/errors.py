"""Agent 台账的领域异常。"""

from __future__ import annotations

from mailbus.core.shared.errors import InvalidStateError


class AgentDisabledError(InvalidStateError):
    """Agent 已停用，不能绑定到员工。"""

    code = "agent_disabled"
