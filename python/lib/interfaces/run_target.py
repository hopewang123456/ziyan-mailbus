"""Run-target runtime ports — Path first (Arch1); Probe/Launch/Cred later."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class RunTargetPathPort(Protocol):
    def resolve(
        self,
        logical_path: str,
        *,
        data_dir: str = "",
        install_root: str = "",
        framework: str = "",
    ) -> str: ...

    def exists(
        self,
        logical_path: str,
        *,
        data_dir: str = "",
        install_root: str = "",
        framework: str = "",
    ) -> bool: ...


@runtime_checkable
class RunTargetAdapter(Protocol):
    name: str

    @property
    def path(self) -> RunTargetPathPort: ...
