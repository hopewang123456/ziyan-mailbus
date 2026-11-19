"""技能包聚合与只读模型。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mailbus.core.skills.values import SkillSourceType, SkillTargetType


@dataclass(frozen=True, slots=True)
class SkillPackage:
    """登记的技能包来源；version 来自最近一次探测。"""

    package_id: str
    name: str
    source_type: SkillSourceType
    source_uri: str
    entry: str = "SKILL.md"
    version: str = ""
    enabled: bool = True
    note: str = ""
    last_checked_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SkillBinding:
    """包与目标的多对多绑定；enabled=False 表示显式停用。"""

    package_id: str
    target_type: SkillTargetType
    target_id: str
    enabled: bool = True
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SkillProbe:
    """来源探测结果：只读取元信息，不复制文件。"""

    reachable: bool
    version: str = ""
    error: str | None = None
