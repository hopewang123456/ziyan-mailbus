"""大屏密钥哈希：只保存 SHA-256 摘要，明文不落库、不回显。"""

from __future__ import annotations

import hashlib
import hmac


class ScreenSecretHasher:
    def digest(self, secret: str) -> str:
        return hashlib.sha256(secret.encode("utf-8")).hexdigest()

    def verify(self, stored: str | None, secret: str | None) -> bool:
        if not stored or not secret:
            return False
        return hmac.compare_digest(stored, self.digest(secret))
