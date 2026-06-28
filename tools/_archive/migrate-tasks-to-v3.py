#!/usr/bin/env python3
"""一次性迁移 store/tasks/*.json：planned_agents → planned_role_types，to_person → to_agent。"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    import fcntl  # noqa: F401
except ImportError:
    from unittest.mock import MagicMock
    sys.modules["fcntl"] = MagicMock()

import contextlib
import lib.utils as _utils


@contextlib.contextmanager
def _noop_file_lock(timeout=10.0, path=""):
    yield


if not hasattr(_utils, "_real_file_lock"):
    _utils._real_file_lock = _utils.file_lock
_utils.file_lock = _noop_file_lock

from lib.pipeline_chain import AGENT_ROLE, agent_to_role
from lib.locale.role_labels import zh_to_role_type, load_role_types


def _agent_to_role_type(agent_id: str, data_dir: str) -> int | None:
    zh = AGENT_ROLE.get(agent_id)
    if zh:
        rt = zh_to_role_type(zh, data_dir)
        if rt is not None:
            return rt
    for rt, info in load_role_types(data_dir).items():
        if agent_id in (info.get("candidates") or []):
            return rt
    return None


def migrate_step(step: dict, data_dir: str) -> bool:
    changed = False
    if step.get("to_person") and not step.get("to_agent"):
        step["to_agent"] = step["to_person"]
        changed = True
    if step.get("to_role") and not step.get("role_type"):
        rt = zh_to_role_type(step["to_role"], data_dir)
        if rt is not None:
            step["role_type"] = rt
            changed = True
    if step.get("from_person") and not step.get("from_agent"):
        step["from_agent"] = step["from_person"]
        changed = True
    return changed


def migrate_task(task: dict, data_dir: str) -> bool:
    changed = False
    chain = task.get("chain") or []
    if not chain:
        return False
    head = chain[0]
    if head.get("planned_agents") and not head.get("planned_role_types"):
        rts = []
        for a in head["planned_agents"]:
            rt = _agent_to_role_type(a, data_dir)
            if rt is not None:
                rts.append(rt)
        if rts:
            head["planned_role_types"] = rts
            changed = True

    for step in chain:
        if isinstance(step, dict) and migrate_step(step, data_dir):
            changed = True

    if task.get("summary") and not task.get("intent"):
        task["intent"] = task["summary"]
        changed = True
    return changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=os.path.join(ROOT, "store"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    data_dir = os.path.abspath(args.data_dir)
    tasks_dir = os.path.join(data_dir, "tasks")
    if not os.path.isdir(tasks_dir):
        print(f"no tasks dir: {tasks_dir}", file=sys.stderr)
        return 1

    backup = os.path.join(tasks_dir, ".backup-pre-v3")
    if not args.dry_run and not os.path.isdir(backup):
        os.makedirs(backup, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        stamp_dir = os.path.join(backup, ts)
        shutil.copytree(tasks_dir, stamp_dir, ignore=shutil.ignore_patterns(".backup-pre-v3", "*.bak*"))
        print(f"backup -> {stamp_dir}")

    n = 0
    for name in sorted(os.listdir(tasks_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(tasks_dir, name)
        with open(path, encoding="utf-8") as f:
            task = json.load(f)
        if not migrate_task(task, data_dir):
            continue
        n += 1
        print(f"  migrate {name}")
        if not args.dry_run:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(task, f, ensure_ascii=False, indent=2)

    print(f"done: {n} task(s){' (dry-run)' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
