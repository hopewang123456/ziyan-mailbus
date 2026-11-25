"""契约共用形状：统一列表包装、成功回执与错误结构。"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """所有列表统一 `{items,total,limit,offset}`，禁止裸数组。"""

    items: list[T]
    total: int
    limit: int
    offset: int


class OkOut(BaseModel):
    ok: bool = True


class ErrorOut(BaseModel):
    """错误结构；契约桩固定返回 error_code=NOT_IMPLEMENTED。"""

    error: str
    error_code: str
    message_zh: str
