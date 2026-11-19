"""技能包上下文的领域异常。"""

from __future__ import annotations

from mailbus.core.shared.errors import DomainError


class SkillSourceInvalidError(DomainError):
    """来源类型或地址不合法。"""

    code = "skill_source_invalid"
