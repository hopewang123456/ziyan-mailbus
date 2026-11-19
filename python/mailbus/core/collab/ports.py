"""协同上下文的持久化端口：大屏、结对与事件总线。"""

from __future__ import annotations

from typing import Protocol, Self

from mailbus.core.collab.models import Pair, Screen
from mailbus.core.identity.ports import EmployeeRepository


class ScreenRepository(Protocol):
    def list_all(self) -> list[Screen]: ...

    def get(self, screen_id: str) -> Screen | None: ...

    def save(self, screen: Screen) -> None: ...


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

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type, exc, tb) -> bool: ...

    def commit(self) -> None: ...
