"""Wave2 orchestration ports."""
from __future__ import annotations

from typing import Any, Mapping, Optional, Protocol, runtime_checkable


@runtime_checkable
class TaskFsmPort(Protocol):
    def ensure(self, task: dict) -> dict: ...

    def is_executable(self, task: dict) -> bool: ...

    def pause(self, task: dict, reason: str = "") -> dict: ...

    def resume(self, task: dict) -> dict: ...

    def bump_retry(self, task: dict, *, step_id: str = "") -> int: ...

    def summary(self, task: dict) -> dict: ...

    def get_active_step(self, task: dict) -> Optional[dict]: ...

    def mark_step_dispatched(self, step: dict) -> None: ...

    def apply_submit(
        self,
        task: dict,
        result: dict,
        *,
        agents: Optional[dict] = None,
        data_dir: str = "",
    ) -> dict: ...

    def apply_rollback(
        self,
        task: dict,
        *,
        to_step: Optional[int] = None,
        to_person: Optional[str] = None,
        reason: str = "",
    ) -> dict: ...

    def read_step_result(self, data_dir: str, task_id: str, step: dict) -> Optional[dict]: ...

    def write_step_result(
        self,
        data_dir: str,
        task_id: str,
        step: dict,
        result: dict,
        *,
        immediate_advance: bool = True,
    ) -> str: ...

    def result_applies_to_step(
        self,
        result: dict,
        task_id: str,
        step: dict,
        chain: list,
        *,
        result_mtime_ok: bool = True,
    ) -> tuple[bool, str]: ...

    def result_mtime_ok(
        self, data_dir: str, task_id: str, step: dict, result: dict,
    ) -> bool: ...

    def step_result_path(self, data_dir: str, task_id: str, step_id: str) -> str: ...

    def legacy_result_path(self, data_dir: str, task_id: str) -> str: ...

    def step_result_dir(self, data_dir: str, task_id: str) -> str: ...

    def archive_step_result_for_retry(
        self, data_dir: str, task_id: str, step: dict, result: dict,
    ) -> str: ...

    def revert_failed_retry(
        self,
        data_dir: str,
        task_id: str,
        step: dict,
        result: dict,
        *,
        archived_path: str = "",
    ) -> None: ...

    def revert_failed_advance(
        self, task: dict, completed_step: dict, next_step: dict,
    ) -> None: ...

    def append_history(self, task: dict, event: str, detail: dict) -> None: ...


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
