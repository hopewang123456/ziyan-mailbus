"""协同上下文的持久化端口：大屏、结对与事件总线。"""

from __future__ import annotations

from typing import Protocol, Self

from mailbus.core.collab.models import Pair, Screen
from mailbus.core.identity.ports import EmployeeRepository
from mailbus.core.shared.ports import AuditPort


class ScreenRepository(Protocol):
    def list_page(self, limit: int, offset: int) -> list[Screen]: ...

    def count(self) -> int: ...

    def list_all(self, limit: int | None = None) -> list[Screen]: ...

    def get(self, screen_id: str) -> Screen | None: ...

    def save(self, screen: Screen) -> None: ...

    def delete(self, screen_id: str) -> None: ...


class PairRepository(Protocol):
    def list_pairs(
        self,
        *,
        state: str | None = None,
        viewer_id: str | None = None,
        limit: int = 100,
    ) -> list[Pair]:
        """按状态与参与者过滤，viewer_id=None 表示不限可见范围。"""

    def find_active_between(self, left_id: str, right_id: str) -> Pair | None: ...

    def get(self, pair_id: str) -> Pair | None: ...

    def save(self, pair: Pair) -> None: ...


class CollabEventBus(Protocol):
    def publish(self, kind: str, payload: dict) -> None: ...


class CollabUnitOfWork(Protocol):
    screens: ScreenRepository
    pairs: PairRepository
    employees: EmployeeRepository
    audit: AuditPort

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type, exc, tb) -> bool: ...

    def commit(self) -> None: ...
