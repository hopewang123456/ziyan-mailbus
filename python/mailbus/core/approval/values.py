"""审批上下文的枚举。

三档语义：
- blocking：请求即阻塞任务，必须裁决后才能继续；
- advisory：不阻塞任务，裁决只作记录；
- informational：仅通知，创建即确认，无需裁决。
"""

from __future__ import annotations

from enum import Enum

DEFAULT_TIMEOUT_MINUTES = 30


class ApprovalTier(str, Enum):
    BLOCKING = "blocking"
    ADVISORY = "advisory"
    INFORMATIONAL = "informational"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    ACKNOWLEDGED = "acknowledged"
    WITHDRAWN = "withdrawn"
