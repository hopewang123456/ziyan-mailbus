#!/usr/bin/env python3
"""Prepare game-courier live run: cancel stale primary, update iteration-state."""
from __future__ import annotations

import json
import os
import sys

MAIL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE = os.path.join(MAIL, "store")
OLD = "game-stellar-v3-20260617"
NEW = "game-courier-20260625"


def main() -> int:
    old_p = os.path.join(STORE, "tasks", f"{OLD}.json")
    if os.path.isfile(old_p):
        t = json.load(open(old_p, encoding="utf-8"))
        if t.get("status") in ("pending", "running"):
            t["status"] = "cancelled"
            t["error"] = {"reason": f"superseded by {NEW}"}
            json.dump(t, open(old_p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            print("cancelled", OLD)

    ist = os.path.join(STORE, "iterations", "iteration-state.json")
    st = json.load(open(ist, encoding="utf-8"))
    st["primary_task_id"] = NEW
    gate = st.get("gate") or {}
    gate["primary_task_id"] = NEW
    gate["primary_status"] = "running"
    gate["blockers"] = []
    st["gate"] = gate
    st["note"] = "live acceptance game-courier-20260625"
    json.dump(st, open(ist, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("primary ->", NEW)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
