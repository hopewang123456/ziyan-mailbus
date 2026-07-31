"""TaskFsmPort adapter over lib.adapters.orchestration.task_fsm."""
from __future__ import annotations

from typing import Any, Optional

from lib.domain.fsm import TaskFsmState
from lib.adapters.orchestration import task_fsm as fsm


class TaskFsmAdapter:
    def ensure(self, task: dict) -> dict:
        return fsm.ensure_fsm(task)

    def is_executable(self, task: dict) -> bool:
        return fsm.is_task_executable(task)

    def pause(self, task: dict, reason: str = "") -> dict:
        return fsm.apply_pause(task, reason=reason)

    def resume(self, task: dict) -> dict:
        fsm.ensure_fsm(task)
        st = task.setdefault("fsm", {})
        if st.get("state") != TaskFsmState.PAUSED.value:
            return {"ok": True, "action": "noop", "task": task}
        st["state"] = TaskFsmState.EXECUTING.value
        task["status"] = "running"
        reason = task.pop("pause_reason", None)
        hist = st.setdefault("history", [])
        hist.append({"event": "resume", "reason": reason})
        return {"ok": True, "action": "resume", "task": task}

    def bump_retry(self, task: dict, *, step_id: str = "") -> int:
        """Q7: retry counters live on task JSON."""
        fsm.ensure_fsm(task)
        st = task.setdefault("fsm", {})
        retries = st.setdefault("retries", {})
        key = step_id or "_task"
        n = int(retries.get(key) or 0) + 1
        retries[key] = n
        st["retry_total"] = int(st.get("retry_total") or 0) + 1
        if step_id:
            for step in task.get("chain") or []:
                if isinstance(step, dict) and step.get("step_id") == step_id:
                    step["retry_count"] = n
                    break
        return n

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

    def legacy_result_path(self, data_dir: str, task_id: str) -> str:
        return fsm.legacy_result_path(data_dir, task_id)

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
