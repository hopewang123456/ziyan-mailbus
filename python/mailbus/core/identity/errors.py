"""身份上下文的领域异常。"""

from __future__ import annotations

from mailbus.core.shared.errors import DomainError


class InviteInvalidError(DomainError):
    """邀请码不存在、已过期或已被消费。"""

    code = "invite_invalid"


class BootstrapLockedError(DomainError):
    """引导完成后不允许再走公开引导入口。"""

    code = "bootstrap_locked"
