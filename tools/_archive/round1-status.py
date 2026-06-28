#!/usr/bin/env python3
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.tracker import TaskTracker
from lib.iteration_engine import evaluate_round1_gate, load_primary_task_id
from lib.utils import json_read

DATA = os.environ.get("MAILBUS_DATA", "store")
TASK = load_primary_task_id(os.path.abspath(DATA))
t = TaskTracker(DATA).get(TASK)
print("=== Round1 状态 ===")
print("task status:", (t or {}).get("status", "NOT FOUND"))
chain = (t or {}).get("chain") or []
if chain:
    print("chain step:", chain[-1].get("to_person"), chain[-1].get("status"))
result = f"store/msg-results/{TASK}.json"
print("msg-results:", "YES" if os.path.exists(result) else "NO")
agents = json_read("store/config.json", {}).get("agents", {})
gate = evaluate_round1_gate(DATA, agents)
print("round2_unlocked:", gate.get("round2_unlocked"))
for b in gate.get("blockers", [])[:5]:
    print(" blocker:", b)
