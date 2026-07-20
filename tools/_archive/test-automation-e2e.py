#!/usr/bin/env python3
"""S 级 test fail→dev 自动化验收（零 plan_approval 人工项）。

  python tools/test-automation-e2e.py
  python tools/test-automation-e2e.py --rounds 3
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from lib.automation import gate_requires_human, load_automation_config, test_fail_auto_to_dev
from lib.human_queue import list_items, load_queue
from lib.task_fsm import apply_submit, create_next_step, ensure_fsm
from lib.utils import json_write


def _minimal_store(tmp: str) -> None:
    cfg_src = os.path.join(ROOT, "store", "config.json")
    with open(cfg_src, encoding="utf-8") as f:
        cfg = json.load(f)
    os.makedirs(tmp, exist_ok=True)
    json_write(os.path.join(tmp, "config.json"), cfg)
    json_write(
        os.path.join(tmp, "human-queue.json"),
        {"version": "1.0.0", "updated_at": "2026-06-18T00:00:00+08:00", "items": []},
    )
    roles = os.path.join(ROOT, "store", "roles")
    dst = os.path.join(tmp, "roles")
    if os.path.isdir(roles):
        shutil.copytree(roles, dst, dirs_exist_ok=True)


def _make_s_task() -> dict:
    task = {
        "task_id": "auto-e2e-test",
        "tier": "S",
        "intent": "automation e2e",
        "chain": [],
        "fsm": {},
    }
    ensure_fsm(task)
    dev = create_next_step(
        task, to_role="开发工程师", to_person="lingxiao",
        from_role="调度员", from_person="xiaoqi", role_type=8,
    )
    dev["step"] = 1
    task["chain"].append(dev)
    task["fsm"]["active_step_id"] = dev["step_id"]
    task["assignee"] = "lingxiao"
    task["fsm"]["state"] = "executing"
    return task


def _advance_to_tester(task: dict, data_dir: str) -> None:
    """dev done -> tester step."""
    r = apply_submit(
        task,
        {"task_id": task["task_id"], "conclusion": "done", "summary": "dev ok"},
        data_dir=data_dir,
    )
    assert r.get("ok"), r
    tester = create_next_step(
        task, to_role="测试工程师", to_person="lingyan",
        from_role="开发工程师", from_person="lingxiao", role_type=6,
    )
    tester["step"] = len(task["chain"]) + 1
    task["chain"].append(tester)
    task["fsm"]["active_step_id"] = tester["step_id"]
    task["assignee"] = "lingyan"
    task["fsm"]["state"] = "executing"


def run_e2e(*, rounds: int = 3) -> int:
    tmp = tempfile.mkdtemp(prefix="mailbus-auto-e2e-")
    try:
        _minimal_store(tmp)
        cfg = load_automation_config(tmp)
        task = _make_s_task()
        _advance_to_tester(task, tmp)

        assert test_fail_auto_to_dev(task, cfg), "S tier should auto retry to dev"
        assert gate_requires_human("publish_go", cfg), "publish_go must stay human"

        hq_before = len(list_items(tmp, status="pending"))
        dev_retries = 0

        for i in range(rounds):
            out = apply_submit(
                task,
                {
                    "task_id": task["task_id"],
                    "conclusion": "fail",
                    "summary": f"test fail round {i + 1}",
                },
                data_dir=tmp,
            )
            if out.get("action") != "advance":
                print(f"[e2e] FAIL round {i + 1}: {out}")
                return 1
            nxt = out.get("next_step") or {}
            if nxt.get("role_type") != 8 and (nxt.get("to_role") or "") != "开发工程师":
                print(f"[e2e] FAIL: expected dev rollback, got {nxt}")
                return 1
            dev_retries += 1
            print(f"[e2e] round {i + 1}: rollback -> {nxt.get('to_person')} ({nxt.get('to_role')})")

            apply_submit(
                task,
                {"task_id": task["task_id"], "conclusion": "done", "summary": "dev fix"},
                data_dir=tmp,
            )
            tester = create_next_step(
                task, to_role="测试工程师", to_person="lingyan",
                from_role="开发工程师", from_person="lingxiao", role_type=6,
            )
            tester["step"] = len(task["chain"]) + 1
            task["chain"].append(tester)
            task["fsm"]["active_step_id"] = tester["step_id"]
            task["assignee"] = "lingyan"
            task["fsm"]["state"] = "executing"

        hq = load_queue(tmp)
        pending = [x for x in hq.get("items", []) if x.get("status") == "pending"]
        plan_items = [x for x in pending if x.get("type") == "plan_approval"]
        new_hq = len(pending) - hq_before

        print(f"[e2e] dev retry rounds={dev_retries}, new human-queue pending={new_hq}, plan_approval={len(plan_items)}")
        if plan_items:
            print("[e2e] FAIL: plan_approval should not appear on test fail loop")
            return 1
        if not gate_requires_human("publish_go", cfg):
            print("[e2e] FAIL: publish_go must require human")
            return 1

        print("[e2e] PASS")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    args = ap.parse_args()
    return run_e2e(rounds=max(1, args.rounds))


if __name__ == "__main__":
    raise SystemExit(main())
