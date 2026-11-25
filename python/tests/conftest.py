"""测试全局环境：提供确定性的 Agent token 加密密钥。"""

from __future__ import annotations

import os

os.environ.setdefault(
    "MAILBUS_TOKEN_ENCRYPTION_KEY", "test-only-token-encryption-key-32bytes"
)
