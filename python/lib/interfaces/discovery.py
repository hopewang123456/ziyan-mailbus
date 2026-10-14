from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from lib.domain.types import DiscoveredAgent


@runtime_checkable
class DiscoverySource(Protocol):
    def scan(self) -> Sequence[DiscoveredAgent]: ...
