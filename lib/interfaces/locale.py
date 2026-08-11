"""Locale port — language string lookup / load + role labels."""
from __future__ import annotations

from typing import Mapping, Protocol, Sequence, runtime_checkable


@runtime_checkable
class LocalePort(Protocol):
    """Locale surface (error codes, role labels, generic keys)."""

    def get(self, key: str, *, fallback: str = "", lang: str = "zh") -> str: ...

    def load(self, lang: str = "zh") -> Mapping[str, str]: ...

    def message_zh(self, code: str, fallback: str = "") -> str: ...

    def role_type_to_zh(self, role_type: int) -> str: ...

    def role_type_candidates(self, role_type: int) -> Sequence[str]: ...

    def valid_role_types(self) -> Sequence[int]: ...
