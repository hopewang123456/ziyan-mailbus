"""Reserved ports: HumanGate (D10) + Audit (D14) — Protocol only until thick use-cases land."""
from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class HumanGatePort(Protocol):
    """人机队列门控（enqueue / resolve）。厚业务仍在 lib.human_queue*，经 Adapter 暴露。"""

    def enqueue(self, item: Mapping[str, Any]) -> str: ...

    def resolve(self, item_id: str, body: Mapping[str, Any]) -> dict:
        """返回 ``{"item": ..., "side": ...}``；未找到时 item 为 None。"""
        ...

    def load_queue(self) -> dict: ...


@runtime_checkable
class AuditPort(Protocol):
    """审计事件流（D14）。默认可 Noop；合规需要时换 FileAuditAdapter。"""

    def append(self, event: str, payload: Mapping[str, Any] | None = None) -> None: ...
