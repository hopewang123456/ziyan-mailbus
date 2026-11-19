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


@dataclass(frozen=True, slots=True)
class AgentSummary:
    """跨上下文只读投影：布局与员工视图只需要名称与框架。"""

    agent_id: str
    name: str
    framework: str
