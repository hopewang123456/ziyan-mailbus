"""Generic feeder: dispatch a station-addressed work order into the real store.

Usage:
  python tools/_game_order.py <task_id> <station> <pin_agent> <intent-file> [step2_station step2_pin step2_intent-file ...]
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "store")

from lib.application.orchestration.router.envelope_validate import validate_envelope
from lib.application.orchestration.router.planner import plan_tier0
from lib.application.orchestration.tracker import TaskTracker
from lib.application.workflow.engine import bind_workflow
from lib.application.orchestration.router.dispatch import dispatch_first_step, start_executing
from lib.infra.utils import json_write


def feed(task_id: str, chain: list[dict], intent: str) -> dict:
    envelope = {
        "task_id": task_id,
        "intent": intent,
        "initiator": "ziyan(proxy)",
        "mode": "explicit",
        "tier": "M",
        "task_type": "custom",
        "planned_chain": chain,
    }
    errors = validate_envelope(envelope, data_dir=DATA_DIR)
    if errors:
        return {"ok": False, "error": f"envelope: {errors}"}
    out = plan_tier0(envelope, data_dir=DATA_DIR)
    tracker = TaskTracker(DATA_DIR)
    existing = tracker.get(task_id)
    if existing and existing.get("status") != "cancelled":
        return {"ok": False, "error": "task_exists"}
    task = tracker.create_from_envelope(
        envelope, planned_chain=out["planned_chain"], plan_meta=out["plan_meta"]
    )
    bind_workflow(task, envelope, data_dir=DATA_DIR)
    json_write(tracker._task_path(task_id), task)
    start_executing(task)
    ok = dispatch_first_step(DATA_DIR, task)
    step = (task.get("chain") or [{}])[0]
    return {
        "ok": ok,
        "assignee": step.get("to_agent"),
        "station": step.get("station"),
        "audit_reviewer": task.get("audit_reviewer"),
    }


def main() -> int:
    args = sys.argv[1:]
    task_id = args[0]
    triples = args[1:]
    assert len(triples) % 3 == 0, "need (station, pin, intent-file) triples"
    chain = []
    for i in range(0, len(triples), 3):
        station, pin, intent_file = triples[i], triples[i + 1], triples[i + 2]
        entry = {"station": station, "reason": "produce"}
        if pin and pin != "-":
            entry["pin_agent"] = pin
        chain.append(entry)
    intent = open(triples[2], encoding="utf-8").read()  # first triple's intent is the order brief
    result = feed(task_id, chain, intent)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
