"""mailbus Transport 层 — A2A wire 与 file_bus 双通道。"""
from .a2a_mapper import from_a2a_task, to_a2a_message
from .types import DispatchContext, DispatchResult

__all__ = [
    "DispatchContext",
    "DispatchResult",
    "TransportRouter",
    "from_a2a_task",
    "to_a2a_message",
]


def __getattr__(name: str):
    if name == "TransportRouter":
        from .router import TransportRouter
        return TransportRouter
    raise AttributeError(name)
