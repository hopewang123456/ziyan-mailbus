from __future__ import annotations

from typing import Protocol, runtime_checkable

from lib.domain.types import PlaneActionResult, ProbeResult


@runtime_checkable
class HostPlanePort(Protocol):
    def start_framework(self, framework: str) -> PlaneActionResult: ...

    def stop_framework(self, framework: str) -> PlaneActionResult: ...

    def probe_framework(self, framework: str) -> ProbeResult: ...


@runtime_checkable
class ContainerPlanePort(Protocol):
    def start_framework(self, framework: str) -> PlaneActionResult: ...

    def stop_framework(self, framework: str) -> PlaneActionResult: ...

    def probe_framework(self, framework: str) -> ProbeResult: ...


@runtime_checkable
class MountMutex(Protocol):
    def assert_exclusive(self, framework: str, mount: str) -> None: ...
