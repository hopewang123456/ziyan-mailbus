"""组织上下文的领域异常。"""

from __future__ import annotations

from mailbus.core.shared.errors import DomainError


class LayoutSeedError(DomainError):
    """布局种子文件缺失或结构非法。"""

    code = "layout_seed_invalid"
