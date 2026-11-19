"""指标治理的聚合与只读模型。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class MetricRule:
    """告警规则：对某个指标值做阈值判断，触发动作由派发器消费。"""

    rule_id: str
    metric: str
    op: str
    threshold: float
    severity: str
    enabled: bool = False
    note: str = ""
    actions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MetricLayout:
    """大盘布局：只记录被隐藏的指标 id。"""

    hidden: tuple[str, ...] = field(default_factory=tuple)
