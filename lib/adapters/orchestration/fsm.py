"""TaskFsmPort adapter over lib.task_fsm (Q7 retry on task JSON)."""
from __future__ import annotations

from typing import Any

from lib.domain.errors import PAUSE_REASON_BUDGET
from lib.adapters.orchestration.task_fsm import (
    TaskFsmState,
    apply_pause,
    ensure_fsm,
    fsm_summary,
    is_task_executable,
)


class TaskFsmAdapter:
    def ensure(self, task: dict) -> dict:
        return ensure_fsm(task)

    def is_executable(self, task: dict) -> bool:
        return is_task_executable(task)

    def pause(self, task: dict, reason: str = "") -> dict:
        return apply_pause(task, reason=reason)

    def resume(self, task: dict) -> dict:
        ensure_fsm(task)
        fsm = task.setdefault("fsm", {})
        if fsm.get("state") != TaskFsmState.PAUSED.value:
            return {"ok": True, "action": "noop", "task": task}
        fsm["state"] = TaskFsmState.EXECUTING.value
        task["status"] = "running"
        reason = task.pop("pause_reason", None)
        hist = fsm.setdefault("history", [])
        hist.append({"event": "resume", "reason": reason})
        return {"ok": True, "action": "resume", "task": task}

    def bump_retry(self, task: dict, *, step_id: str = "") -> int:
        """Q7: retry counters live on task JSON."""
        ensure_fsm(task)
        fsm = task.setdefault("fsm", {})
        retries = fsm.setdefault("retries", {})
        key = step_id or "_task"
        n = int(retries.get(key) or 0) + 1
        retries[key] = n
        fsm["retry_total"] = int(fsm.get("retry_total") or 0) + 1
        # mirror on active step if present
        if step_id:
            for step in task.get("chain") or []:
                if isinstance(step, dict) and step.get("step_id") == step_id:
                    step["retry_count"] = n
                    break
        return n

    def summary(self, task: dict) -> dict:
        return fsm_summary(task)
