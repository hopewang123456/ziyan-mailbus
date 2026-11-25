"""Agent token 的加密与不可逆反查摘要。

明文永不落库：DB 只存 AES-GCM 密文 + HMAC 反查摘要。
密文格式 `enc:<base64url(nonce|ct)>`，与 Java 端实现互通。
密钥来自 MAILBUS_TOKEN_ENCRYPTION_KEY；缺失时由 Container.start 快速失败。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_PREFIX = "enc:"
_AAD = b"mailbus-agent-token"
_NONCE_BYTES = 12


class TokenConfigurationError(RuntimeError):
    """缺少或非法密钥：启动期 fail fast。"""


class TokenCipher:
    def __init__(self, key_material: str | None) -> None:
        self._secret = (key_material or "").strip()
        self._aes: AESGCM | None = None
        self._lookup_key = b""
        if self._secret:
            digest = hashlib.sha256(self._secret.encode("utf-8")).digest()
            self._aes = AESGCM(digest)
            self._lookup_key = hashlib.sha256(digest + b":lookup").digest()

    @classmethod
    def from_env(cls) -> "TokenCipher":
        return cls(os.environ.get("MAILBUS_TOKEN_ENCRYPTION_KEY"))

    @property
    def available(self) -> bool:
        return self._aes is not None

    def require(self) -> None:
        if not self.available:
            raise TokenConfigurationError(
                "缺少 MAILBUS_TOKEN_ENCRYPTION_KEY，无法处理 Agent token"
            )

    def encrypt(self, plaintext: str) -> str:
        self.require()
        assert self._aes is not None
        nonce = os.urandom(_NONCE_BYTES)
        ciphertext = self._aes.encrypt(nonce, plaintext.encode("utf-8"), _AAD)
        packed = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii").rstrip("=")
        return _PREFIX + packed

    def decrypt(self, ciphertext: str | None) -> str | None:
        if not ciphertext:
            return None
        self.require()
        assert self._aes is not None
        packed = ciphertext[len(_PREFIX):] if ciphertext.startswith(_PREFIX) else ciphertext
        try:
            raw = base64.urlsafe_b64decode(_pad(packed))
            nonce, body = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
            return self._aes.decrypt(nonce, body, _AAD).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None

    def lookup_digest(self, plaintext: str) -> str:
        self.require()
        return hmac.new(self._lookup_key, plaintext.encode("utf-8"), hashlib.sha256).hexdigest()

    def fingerprint(self, plaintext: str) -> str:
        digest = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
        return digest[:12]


def _pad(value: str) -> bytes:
    return (value + "=" * (-len(value) % 4)).encode("ascii")
