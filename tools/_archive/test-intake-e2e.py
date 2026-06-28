#!/usr/bin/env python3
"""商前 intake 全链路 E2E（API 层，无 HTTP 服务器）。

场景 A 子集：spawn-analyze → G1 approve → solution task → content spawn
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import sys
import tempfile
from unittest.mock import MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.modules.setdefault("fcntl", MagicMock())

import lib.utils as _utils


@contextlib.contextmanager
def _noop_file_lock(timeout=10.0, path=""):
    yield


_utils.file_lock = _noop_file_lock

from lib.intake.gates import on_intake_gate_approve
from lib.intake.spawn_rules import bridge_reconcile
from lib.intake.store import get, upsert
from lib.intake.task_bridge import spawn_analyze
from lib.tracker import TaskTracker
from lib.utils import json_write


def _seed(tmp: str) -> str:
    store = os.path.join(ROOT, "store")
    for sub in ("roles/json", "workflows", "dispatch", "rules", "leads", "inbox/dali", "inbox/lingxiao", "msg-files"):
        src = os.path.join(store, sub)
        dst = os.path.join(tmp, sub)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
    os.makedirs(os.path.join(tmp, "tasks"), exist_ok=True)
    json_write(os.path.join(tmp, "inbox", "dali", "inbox.json"), {"agent": "dali", "messages": []})
    json_write(os.path.join(tmp, "inbox", "lingxiao", "inbox.json"), {"agent": "lingxiao", "messages": []})
    json_write(os.path.join(tmp, "human-queue.json"), {"version": "1.0.0", "updated_at": "2026-06-18T00:00:00+08:00", "items": []})
    json_write(os.path.join(tmp, "config.json"), {
        "mailbus_intake_bridge": {"enabled": True, "auto_spawn_analyze": True},
        "mailbus_internal_llm": {"enabled": False, "guardrails": {"await_plan_approval_tier_min": "L"}},
        "mailbus_workflow": {"tool_live": False},
    })
    example = os.path.join(store, "examples", "order-intake.pursue.example.json")
    with open(example, encoding="utf-8") as f:
        intake = json.load(f)
    intake["decision"] = "pending"
    intake["pipeline_link"] = {}
    for g in intake.get("commercial_gates") or []:
        if g.get("gate_id") == "req_to_lingzhao":
            g["status"] = "pending"
    json_write(os.path.join(tmp, "leads", "order-intake.json"), [intake])
    return intake["intake_id"]


def run_e2e(data_dir: str) -> dict:
    intake_id = None
    for item in json.load(open(os.path.join(data_dir, "leads", "order-intake.json"), encoding="utf-8")):
        intake_id = item.get("intake_id")
        break
    if not intake_id:
        raise RuntimeError("no intake seeded")

    steps = []

    # R1 / spawn-analyze
    bridge = bridge_reconcile(data_dir)
    steps.append({"step": "bridge_reconcile", "ok": bridge["status"] == "ok"})
    tr = TaskTracker(data_dir)
    intake = get(data_dir, intake_id)
    analyze_tid = (intake.get("pipeline_link") or {}).get("intake_task_id")
    steps.append({"step": "spawn_analyze", "ok": bool(analyze_tid and tr.get(analyze_tid))})

    # simulate analyze done → pursue
    intake = get(data_dir, intake_id)
    intake["decision"] = "pursue"
    for g in intake.get("commercial_gates") or []:
        if g.get("gate_id") == "req_to_lingzhao":
            g["status"] = "pending"
    upsert(data_dir, intake)

    # G1 approve → solution
    outcome = on_intake_gate_approve(data_dir, intake_id, "req_to_lingzhao", {
        "reviewer": "human",
        "brief": "E2E 商单需求包",
        "attachments": [{"kind": "file", "ref": "/tmp/req.md", "label": "需求"}],
    })
    sol_tid = outcome.get("spawned_task_id")
    task = tr.get(sol_tid) if sol_tid else None
    steps.append({
        "step": "G1_req_to_lingzhao",
        "ok": outcome.get("ok") and task and task["chain"][0].get("role_type") == 1,
        "task_id": sol_tid,
    })

    ext = (task or {}).get("extensions") or {}
    ziyan = ext.get("ziyan") or {}
    steps.append({
        "step": "extensions_nested",
        "ok": ziyan.get("intake", {}).get("intake_id") == intake_id,
    })

    # G4 content
    intake = get(data_dir, intake_id)
    for g in intake.get("commercial_gates") or []:
        if g.get("gate_id") == "content_start":
            g["status"] = "approved"
            g["attachments"] = [{"kind": "file", "ref": "/tmp/topic.md", "label": "选题"}]
    upsert(data_dir, intake)
    from lib.intake.task_bridge import spawn_by_kinds
    content = spawn_by_kinds(data_dir, intake_id, ["content"])
    vid = content.get("spawned", {}).get("content")
    steps.append({"step": "G4_content_spawn", "ok": bool(vid and vid.startswith("vid-"))})

    failed = [s for s in steps if not s.get("ok")]
    return {"intake_id": intake_id, "steps": steps, "passed": len(steps) - len(failed), "failed": len(failed)}


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="intake-e2e-")
    try:
        _seed(tmp)
        result = run_e2e(tmp)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result["failed"]:
            print(f"E2E FAILED: {result['failed']} step(s)", file=sys.stderr)
            return 1
        print(f"E2E OK: {result['passed']} steps")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
