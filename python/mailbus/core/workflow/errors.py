"""流程上下文的领域异常。"""

from __future__ import annotations

from mailbus.core.shared.errors import InvalidStateError


class VersionNotPublishedError(InvalidStateError):
    """任务只能从已发布版本创建。"""

    code = "version_not_published"
