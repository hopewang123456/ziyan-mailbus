"""技能包上下文的枚举与常量。

来源只支持本地路径与 http(s)；不做安装、复制或运行时执行。
"""

from __future__ import annotations

from enum import Enum

MAX_NAME_LENGTH = 64
MAX_URI_LENGTH = 512
DEFAULT_ENTRY = "SKILL.md"

# PATCH 允许修改的字段；来源变更会重置探测结果。
PATCHABLE_FIELDS: frozenset[str] = frozenset(
    {"name", "source_type", "source_uri", "entry", "note", "enabled"}
)
SOURCE_FIELDS: frozenset[str] = frozenset({"source_type", "source_uri", "entry"})


class SkillSourceType(str, Enum):
    LOCAL = "local"
    HTTP = "http"


class SkillTargetType(str, Enum):
    """绑定的目标：Agent 台账（默认）或员工（覆盖）。"""

    AGENT = "agent"
    EMPLOYEE = "employee"
