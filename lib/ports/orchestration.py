"""Wave2 orchestration ports."""
from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from lib.domain.types import StepRef


@runtime_checkable
class TaskFsmPort(Protocol):
    def ensure(self, task: dict) -> dict: ...

    def is_executable(self, task: dict) -> bool: ...

    def pause(self, task: dict, reason: str = "") -> dict: ...

    def resume(self, task: dict) -> dict: ...

    def bump_retry(self, task: dict, *, step_id: str = "") -> int: ...

    def summary(self, task: dict) -> dict: ...


@runtime_checkable
class BudgetMeterPort(Protocol):
    def load(self, cfg: Mapping[str, Any] | None = None) -> dict: ...

    def record_spend(self, amount_cny: float, cfg: Mapping[str, Any] | None = None) -> dict: ...

    def apply_ollama_decision(self, use_ollama: bool | None, cfg: Mapping[str, Any] | None = None) -> dict: ...

    def is_paused(self) -> bool: ...


@runtime_checkable
class NotifierPort(Protocol):
    def notify(self, event: str, payload: Mapping[str, Any] | None = None) -> None: ...


@runtime_checkable
class OrchestrationPort(Protocol):
    """Mediator: budget gate + FSM before pipeline advance."""

    def can_advance(self, task: dict) -> tuple[bool, str]: ...

    def on_budget_decision(self, use_ollama: bool | None) -> dict: ...

    def record_spend(self, amount_cny: float) -> dict: ...
