"""Intake → Task spawn（内部 Envelope create）。"""

from __future__ import annotations

import os
from typing import Optional

from ..router.dispatch import dispatch_first_step, set_await_plan_approval, start_executing
from ..router.planner import needs_plan_approval, plan_task
from ..tracker import TaskTracker
from ..utils import json_read, json_write
from ..workflow.engine import bind_workflow
from .gate_sync import copy_approved_intake_gates
from .store import get, upsert


class SpawnError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


def _create_envelope_task(data_dir: str, envelope: dict, *, config: dict) -> dict:
    if envelope.get("mode") == "explicit":
        planned = envelope["planned_chain"]
        plan_meta = {"method": "rules", "task_type_guess": envelope.get("task_type"), "confidence": 1.0, "provider_used": "rules"}
    else:
        out = plan_task(envelope, data_dir=data_dir, config=config)
        planned = out["planned_chain"]
        plan_meta = out["plan_meta"]

    tracker = TaskTracker(data_dir)
    task_id = envelope["task_id"]
    if tracker.get(task_id):
        raise SpawnError("task_exists", task_id)

    task = tracker.create_from_envelope(envelope, planned_chain=planned, plan_meta=plan_meta)
    bind_workflow(task, envelope, data_dir=data_dir)

    if needs_plan_approval(envelope, config):
        set_await_plan_approval(task)
        from ..human_queue import enqueue_plan_approval
        hq_id = enqueue_plan_approval(data_dir, task)
        task["fsm"]["human_queue_id"] = hq_id
    else:
        start_executing(task)
        dispatch_first_step(data_dir, task)

    json_write(tracker._task_path(task_id), task)
    return task


def spawn_analyze(data_dir: str, intake_id: str, *, force: bool = False) -> dict:
    intake = get(data_dir, intake_id)
    if not intake:
        raise SpawnError("not_found", intake_id)
    link = intake.get("pipeline_link") or {}
    task_id = f"{intake_id}-analyze"
    if link.get("intake_task_id") and not force:
        raise SpawnError("already_spawned", link["intake_task_id"])

    config = json_read(os.path.join(data_dir, "config.json"), {})
    envelope = {
        "protocol_version": "mailbus-a2a/1",
        "task_id": task_id,
        "intent": f"商前研判 {intake_id}：{intake.get('title', '')[:80]}",
        "initiator": "mailbus",
        "mode": "explicit",
        "tier": "S",
        "task_type": "intake",
        "planned_chain": [{"role_type": 4}],
        "extensions": {
            "ziyan": {
                "workflow": {"workflow_id": "intake_analyze", "phase": "analyze"},
                "intake": {
                    "intake_id": intake_id,
                    "spawn_kind": "analyze",
                    "source_platform": intake.get("source_platform"),
                },
            },
        },
    }
    task = _create_envelope_task(data_dir, envelope, config=config)
    link = dict(intake.get("pipeline_link") or {})
    link["intake_task_id"] = task_id
    intake["pipeline_link"] = link
    upsert(data_dir, intake)
    return {"task_id": task_id, "task": task}


def spawn_commercial_design(data_dir: str, intake: dict, *, brief: str = "") -> dict:
    intake_id = intake["intake_id"]
    task_id = f"sol-{intake_id}"
    tracker = TaskTracker(data_dir)
    if tracker.get(task_id):
        raise SpawnError("task_exists", task_id)

    config = json_read(os.path.join(data_dir, "config.json"), {})
    if brief:
        intake["requirements_brief"] = brief
    envelope = {
        "protocol_version": "mailbus-a2a/1",
        "task_id": task_id,
        "intent": brief or intake.get("requirements_brief") or intake.get("title", ""),
        "initiator": "human",
        "mode": "explicit",
        "tier": "M",
        "task_type": "feature",
        "planned_chain": [{"role_type": 1}],
        "extensions": {
            "ziyan": {
                "workflow": {
                    "workflow_id": "commercial_solution",
                    "phase": "design",
                    "gates": [],
                },
                "intake": {
                    "intake_id": intake_id,
                    "spawn_kind": "solution",
                    "source_platform": intake.get("source_platform"),
                },
            },
        },
    }
    task = _create_envelope_task(data_dir, envelope, config=config)
    copy_approved_intake_gates(intake, task)
    json_write(tracker._task_path(task_id), task)

    link = dict(intake.get("pipeline_link") or {})
    link["solution_task_id"] = task_id
    link["solution_phase"] = "design"
    link["chain_type"] = "feature"
    intake["pipeline_link"] = link
    upsert(data_dir, intake)
    return {"task_id": task_id, "spawned_task_id": task_id, "task": task}


def spawn_video_publish(data_dir: str, intake: dict) -> dict:
    intake_id = intake["intake_id"]
    task_id = f"vid-{intake_id}"
    tracker = TaskTracker(data_dir)
    if tracker.get(task_id):
        raise SpawnError("task_exists", task_id)

    config = json_read(os.path.join(data_dir, "config.json"), {})
    hint = intake.get("content_hint") or {}
    envelope = {
        "protocol_version": "mailbus-a2a/1",
        "task_id": task_id,
        "intent": hint.get("hook") or intake.get("title", ""),
        "initiator": "human",
        "mode": "explicit",
        "tier": "M",
        "task_type": "video_publish",
        "planned_chain": [{"role_type": 3}],
        "extensions": {
            "ziyan": {
                "workflow": {"workflow_id": "video_publish", "phase": "research"},
                "intake": {"intake_id": intake_id, "spawn_kind": "content"},
            },
        },
    }
    task = _create_envelope_task(data_dir, envelope, config=config)
    link = dict(intake.get("pipeline_link") or {})
    link["content_task_id"] = task_id
    intake["pipeline_link"] = link
    upsert(data_dir, intake)
    return {"task_id": task_id, "spawned_task_id": task_id, "task": task}


_KIND_GATE = {
    "solution": "req_to_lingzhao",
    "content": "content_start",
}


def _gate_approved(intake: dict, gate_id: str) -> bool:
    for g in intake.get("commercial_gates") or []:
        if g.get("gate_id") == gate_id:
            return g.get("status") == "approved"
    return False


def spawn_by_kinds(data_dir: str, intake_id: str, kinds: list, *, tier: str = "M") -> dict:
    """低层 spawn：须对应 commercial_gate 已 approved。"""
    intake = get(data_dir, intake_id)
    if not intake:
        raise SpawnError("not_found", intake_id)
    if not kinds:
        raise SpawnError("missing_kinds", "kinds required")

    link = intake.get("pipeline_link") or {}
    spawned: dict = {}
    skipped: dict = {}

    for kind in kinds:
        gate_id = _KIND_GATE.get(kind)
        if not gate_id:
            raise SpawnError("invalid_kind", kind)
        if not _gate_approved(intake, gate_id):
            raise SpawnError("gate_not_approved", gate_id)

        if kind == "solution":
            existing = link.get("solution_task_id")
            if existing and TaskTracker(data_dir).get(existing):
                skipped["solution"] = existing
                continue
            try:
                out = spawn_commercial_design(data_dir, intake, brief=intake.get("requirements_brief") or "")
                spawned["solution"] = out["spawned_task_id"]
                intake = get(data_dir, intake_id) or intake
                link = intake.get("pipeline_link") or {}
            except SpawnError as exc:
                if exc.code == "task_exists":
                    skipped["solution"] = link.get("solution_task_id")
                else:
                    raise
        elif kind == "content":
            existing = link.get("content_task_id")
            if existing and TaskTracker(data_dir).get(existing):
                skipped["content"] = existing
                continue
            try:
                out = spawn_video_publish(data_dir, intake)
                spawned["content"] = out["spawned_task_id"]
                intake = get(data_dir, intake_id) or intake
                link = intake.get("pipeline_link") or {}
            except SpawnError as exc:
                if exc.code == "task_exists":
                    skipped["content"] = link.get("content_task_id")
                else:
                    raise

    return {
        "intake_id": intake_id,
        "spawned": spawned,
        "skipped": skipped,
        "pipeline_link": link,
        "tier": tier,
    }
