"""唯一 id 生成（前缀 + uuid4 hex）。"""

from __future__ import annotations

from uuid import uuid4


class UuidGenerator:
    def new(self, prefix: str) -> str:
        return f"{prefix}_{uuid4().hex}"
