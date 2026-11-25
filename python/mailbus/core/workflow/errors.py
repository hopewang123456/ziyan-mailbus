"""流程上下文的领域异常。"""

from __future__ import annotations

from typing import Any

from mailbus.core.shared.errors import DomainError, InvalidStateError, UnprocessableError


class VersionNotPublishedError(InvalidStateError):
    """任务只能从已发布版本创建。"""

    code = "version_not_published"


class GraphInvalidError(DomainError):
    """PUT Graph 的结构性错误（HTTP 400），携带可定位的 issues。"""

    code = "invalid_graph"

    def __init__(self, message_zh: str, issues: tuple[dict[str, Any], ...]) -> None:
        super().__init__(message_zh)
        self.issues = issues


class RevisionConflictError(InvalidStateError):
    """乐观锁冲突；响应体额外带上服务端 revision 供前端提示。"""

    code = "revision_conflict"

    def __init__(self, message_zh: str, revision: int) -> None:
        super().__init__(message_zh)
        self.revision = revision


class PublishValidationError(UnprocessableError):
    """发布前强制校验失败；响应体带上 errors 清单。"""

    code = "publish_invalid"

    def __init__(self, message_zh: str, issues: tuple[dict[str, Any], ...]) -> None:
        super().__init__(message_zh)
        self.issues = issues
