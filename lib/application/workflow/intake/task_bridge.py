"""Intake → pipeline task spawn（analyze / solution / content）。"""

from __future__ import annotations

from lib.application.orchestration.tracker import TaskTracker
from lib.infra.utils import _now_iso
from .store import get, upsert


class SpawnError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _intake_extensions(intake_id: str, workflow_id: str) -> dict:
    return {
        "mailbus": {
            "intake": {"intake_id": intake_id},
            "workflow": {"workflow_id": workflow_id},
        }
    }


def _create_task(
    data_dir: str,
    *,
    task_id: str,
    intake_id: str,
    intent: str,
    task_type: str,
    workflow_id: str,
    planned_chain: list,
    tier: str = "S",
) -> dict:
    from lib.application.workflow.engine import bind_workflow

    tr = TaskTracker(data_dir)
    if tr.get(task_id):
        raise SpawnError("spawn_blocked", f"task_exists:{task_id}")

    envelope = {
        "task_id": task_id,
        "intent": intent,
        "initiator": "mailbus",
        "mode": "explicit",
        "tier": tier,
        "task_type": task_type,
        "planned_chain": planned_chain,
        "extensions": _intake_extensions(intake_id, workflow_id),
    }
    task = tr.create_from_envelope(
        envelope,
        planned_chain=planned_chain,
        plan_meta={"source": "intake_bridge", "created_at": _now_iso()},
    )
    bind_workflow(task, envelope, data_dir=data_dir)
    from lib.infra.utils import json_write
    json_write(tr._task_path(task_id), task)
    return task


def spawn_analyze(data_dir: str, intake_id: str, *, force: bool = False) -> dict:
    intake = get(data_dir, intake_id)
    if not intake:
        raise SpawnError("not_found", intake_id)

    link = dict(intake.get("pipeline_link") or {})
    existing = link.get("intake_task_id")
    if existing and not force:
        return {"task_id": existing, "skipped": "exists"}

    task_id = f"{intake_id}-analyze"
    title = intake.get("title") or intake_id
    _create_task(
        data_dir,
        task_id=task_id,
        intake_id=intake_id,
        intent=f"商前研判 — {title}",
        task_type="intake",
        workflow_id="intake_analyze",
        planned_chain=[{"role_type": 4}],
    )
    link["intake_task_id"] = task_id
    intake["pipeline_link"] = link
    upsert(data_dir, intake)
    return {"task_id": task_id, "spawned_task_id": task_id}


def spawn_commercial_design(data_dir: str, intake: dict, *, brief: str = "") -> dict:
    intake_id = intake.get("intake_id", "")
    if not intake_id:
        raise SpawnError("not_found", "missing intake_id")

    link = dict(intake.get("pipeline_link") or {})
    if link.get("solution_task_id"):
        raise SpawnError("spawn_blocked", "solution_task_exists")

    task_id = f"sol-{intake_id}"
    title = intake.get("title") or intake_id
    if brief:
        intake["requirements_brief"] = brief

    _create_task(
        data_dir,
        task_id=task_id,
        intake_id=intake_id,
        intent=f"商单方案 — {title}",
        task_type="feature",
        workflow_id="commercial_solution",
        planned_chain=[{"role_type": 1}],
    )
    link["solution_task_id"] = task_id
    intake["pipeline_link"] = link
    upsert(data_dir, intake)
    return {"spawned_task_id": task_id, "task_id": task_id}


def spawn_video_publish(data_dir: str, intake: dict, *, tier: str = "M") -> dict:
    intake_id = intake.get("intake_id", "")
    if not intake_id:
        raise SpawnError("not_found", "missing intake_id")

    link = dict(intake.get("pipeline_link") or {})
    if link.get("content_task_id"):
        raise SpawnError("spawn_blocked", "content_task_exists")

    task_id = f"vid-{intake_id}"
    title = intake.get("title") or intake_id
    _create_task(
        data_dir,
        task_id=task_id,
        intake_id=intake_id,
        intent=f"内容发布 — {title}",
        task_type="video_publish",
        workflow_id="video_publish",
        planned_chain=[{"role_type": 3}],
        tier=tier,
    )
    link["content_task_id"] = task_id
    intake["pipeline_link"] = link
    upsert(data_dir, intake)
    return {"spawned_task_id": task_id, "task_id": task_id}


def spawn_by_kinds(data_dir: str, intake_id: str, kinds: list) -> dict:
    intake = get(data_dir, intake_id)
    if not intake:
        raise SpawnError("not_found", intake_id)

    spawned: dict = {}
    for kind in kinds:
        if kind == "solution":
            out = spawn_commercial_design(data_dir, intake)
            intake = get(data_dir, intake_id) or intake
            spawned["solution"] = out["spawned_task_id"]
        elif kind == "content":
            out = spawn_video_publish(data_dir, intake)
            spawned["content"] = out["spawned_task_id"]
    return {"spawned": spawned, **spawned}
