#!/usr/bin/env python3
"""Write mailbus final acceptance report for game-courier live run."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import importlib.util

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.tracker import TaskTracker
from lib.utils import json_read, json_write, resolve_paths, _now_iso


def _collect_postmortem(data_dir: str) -> dict:
    path = os.path.join(os.path.dirname(__file__), "collect-pipeline-postmortem.py")
    spec = importlib.util.spec_from_file_location("collect_pipeline_postmortem", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.collect(data_dir)

TASK_ID = "game-courier-20260625"
REPORT_ID = "mailbus-final-acceptance-20260625"


def _pytest_summary() -> str:
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest",
             "tests/test_pusher_p0_env.py", "tests/test_pipeline_trigger_p0.py",
             "tests/test_v2_regression.py", "tests/test_ack_handler.py", "tests/test_task_fsm.py",
             "-q"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True, timeout=120,
        )
        line = (r.stdout or "").strip().splitlines()[-1] if r.stdout else ""
        return line or f"exit={r.returncode}"
    except Exception as exc:
        return f"error: {exc}"


def main() -> int:
    mail = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(mail, "store")
    tr = TaskTracker(data_dir)
    task = tr.get(TASK_ID) or {}
    chain = task.get("chain") or []
    step = chain[-1] if chain else {}
    step_dir = os.path.join(data_dir, "msg-results", TASK_ID)
    deliverable = os.path.join(data_dir, "deliverables", TASK_ID)

    payload = {
        "template": "report",
        "agent": "mailbus",
        "task_id": REPORT_ID,
        "status": "partial" if task.get("status") != "success" else "done",
        "summary": (
            f"game-courier live 验收进行中：{len([f for f in os.listdir(step_dir) if f.startswith('step-s')]) if os.path.isdir(step_dir) else 0}/12 步已落盘；"
            f"task={task.get('status', '?')} active_step={step.get('step', '?')} "
            f"assignee={step.get('to_agent') or step.get('to_person') or '?'}"
        ),
        "timestamp": _now_iso(),
        "checklist": {
            "pusher_timeout_kill": True,
            "pusher_replies_json_write": True,
            "pipeline_verify_retry_rollback": True,
            "tracker_false_timeout_guard": True,
            "scan_lock_logging": True,
            "ack_orphan_warn": True,
            "ack_timeout_unified_30": True,
            "scanner_to_agent_fix": True,
            "is_task_executable_created_running": True,
            "watch_script_windows": True,
            "pytest_key_suite": _pytest_summary(),
        },
        "game_courier": {
            "task_id": TASK_ID,
            "task_status": task.get("status"),
            "active_step": step.get("step"),
            "assignee": step.get("to_agent") or step.get("to_person"),
            "step_fsm": step.get("fsm_state"),
            "msg_results_step_dir": os.path.isdir(step_dir),
            "deliverable_exists": os.path.isdir(deliverable),
            "watch_log": os.path.join(mail, "logs", f"pipeline-watch-{TASK_ID}.log"),
        },
        "next_actions": [
            "等待 s8 lingjian 审查 → s9 lingyan 测试 → s10-s12 收尾",
            "bus serve / watch 重启以加载 claude_code 直连推送修复",
            "完成后 deliverables/game-courier-20260625/tests/test_smoke.py pytest",
        ],
        "postmortem": _collect_postmortem(data_dir),
    }
    out = os.path.join(data_dir, "msg-results", f"{REPORT_ID}.json")
    json_write(out, payload)
    print(json.dumps({"written": out, "status": payload["status"]}, ensure_ascii=False))
    return 0 if task.get("status") == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
