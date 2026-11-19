"""Agent 上下文的常量。

框架名称保持自由文本（不同运行时可自定义），因此这里不定义枚举；
需要状态枚举时仍只允许放在 core。
"""

from __future__ import annotations

# PATCH 允许修改的字段；未列出的字段一律拒绝，避免客户端改到审计列。
PATCHABLE_FIELDS: frozenset[str] = frozenset(
    {"name", "framework", "model", "endpoint", "enabled"}
)

MAX_NAME_LENGTH = 64
MAX_FRAMEWORK_LENGTH = 64
