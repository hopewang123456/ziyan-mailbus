"""TaskFsmPort adapter over lib.adapters.orchestration.task_fsm."""
from __future__ import annotations

from typing import Any, Optional

from lib.adapters.orchestration import task_fsm as fsm


class TaskFsmAdapter:
    def ensure(self, task: dict, *, default_priority: int = 50) -> dict:
        return fsm.ensure_fsm(task, default_priority=default_priority)

    def is_executable(self, task: dict) -> bool:
        return fsm.is_task_executable(task)

    def pause(self, task: dict, reason: str = "") -> dict:
        return fsm.apply_pause(task, reason=reason)

    def resume(self, task: dict) -> dict:
        return fsm.apply_resume(task)

    def bump_retry(self, task: dict, *, step_id: str = "") -> int:
        return fsm.bump_retry(task, step_id=step_id)

    def summary(self, task: dict) -> dict:
        return fsm.fsm_summary(task)

    def get_active_step(self, task: dict) -> Optional[dict]:
        return fsm.get_active_step(task)

    def mark_step_dispatched(self, step: dict) -> None:
        fsm.mark_step_dispatched(step)

    def apply_submit(
        self,
        task: dict,
        result: dict,
        *,
        agents: Optional[dict] = None,
        data_dir: str = "",
    ) -> dict:
        return fsm.apply_submit(task, result, agents=agents, data_dir=data_dir)

    def apply_rollback(
        self,
        task: dict,
        *,
        to_step: Optional[int] = None,
        to_person: Optional[str] = None,
        reason: str = "",
    ) -> dict:
        return fsm.apply_rollback(
            task, to_step=to_step, to_person=to_person, reason=reason,
        )

    def read_step_result(self, data_dir: str, task_id: str, step: dict) -> Optional[dict]:
        return fsm.read_step_result(data_dir, task_id, step)

    def write_step_result(
        self,
        data_dir: str,
        task_id: str,
        step: dict,
        result: dict,
        *,
        immediate_advance: bool = True,
    ) -> str:
        return fsm.write_step_result(
            data_dir, task_id, step, result, immediate_advance=immediate_advance,
        )

    def result_applies_to_step(
        self,
        result: dict,
        task_id: str,
        step: dict,
        chain: list,
        *,
        result_mtime_ok: bool = True,
    ) -> tuple[bool, str]:
        return fsm.result_applies_to_step(
            result, task_id, step, chain, result_mtime_ok=result_mtime_ok,
        )

    def result_mtime_ok(
        self, data_dir: str, task_id: str, step: dict, result: dict,
    ) -> bool:
        return fsm.result_mtime_ok(data_dir, task_id, step, result)

    def step_result_path(self, data_dir: str, task_id: str, step_id: str) -> str:
        return fsm.step_result_path(data_dir, task_id, step_id)

    def step_result_dir(self, data_dir: str, task_id: str) -> str:
        return fsm.step_result_dir(data_dir, task_id)

    def archive_step_result_for_retry(
        self, data_dir: str, task_id: str, step: dict, result: dict,
    ) -> str:
        return fsm.archive_step_result_for_retry(data_dir, task_id, step, result) or ""

    def revert_failed_retry(
        self,
        data_dir: str,
        task_id: str,
        step: dict,
        result: dict,
        *,
        archived_path: str = "",
    ) -> None:
        fsm.revert_failed_retry(
            data_dir, task_id, step, result, archived_path=archived_path or None,
        )

    def revert_failed_advance(
        self, task: dict, completed_step: dict, next_step: dict,
    ) -> None:
        fsm.revert_failed_advance(task, completed_step, next_step)

    def append_history(self, task: dict, event: str, detail: dict) -> None:
        fsm._append_history(task, event, detail)

    def create_next_step(
        self,
        task: dict,
        *,
        to_role: str,
        to_person: str,
        from_role: str,
        from_person: str,
        rollback_from: Optional[str] = None,
        reason: str = "",
        role_type: Optional[int] = None,
    ) -> dict:
        return fsm.create_next_step(
            task,
            to_role=to_role,
            to_person=to_person,
            from_role=from_role,
            from_person=from_person,
            rollback_from=rollback_from,
            reason=reason,
            role_type=role_type,
        )

    def task_priority(self, task: dict) -> int:
        return fsm.task_priority(task)

    def apply_cancel(
        self,
        task: dict,
        reason: str = "",
        *,
        data_dir: str = "",
        agents: Optional[dict] = None,
    ) -> dict:
        return fsm.apply_cancel(
            task, reason=reason, data_dir=data_dir, agents=agents,
        )
