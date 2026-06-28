#!/bin/bash
# 监控 scheduler 三轮自优化 — pipeline + R2 backlog + scheduler 状态
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${SCRIPT_DIR}/lib/api-url.sh"

MAIL="/mnt/e/ai_tools/mail"
BASE="$MAILBUS_API_BASE"
TASK="${1:-mailbus-scheduler-validation-20260616}"
LOOPS="${2:-12}"
INTERVAL="${3:-30}"

log() { echo "[watch-iter] $*"; }

cd "$MAIL"

for i in $(seq 1 "$LOOPS"); do
  log "=== tick $i/$LOOPS ==="
  curl -s "${BASE}/api/status" -o /tmp/watch-status.json 2>/dev/null || echo '{}' > /tmp/watch-status.json
  python3 <<PY
import json, os, sys
sys.path.insert(0, ".")
from lib.tracker import TaskTracker
from lib.iteration_engine import evaluate_round1_gate

task_id = "${TASK}"
data = "store"
agents = json.load(open("store/config.json")).get("agents", {})
gate = evaluate_round1_gate(data, agents)
t = TaskTracker(data).get(task_id) or {}
st = json.load(open("/tmp/watch-status.json"))
sched = st.get("scheduler") or {}
scan = (sched.get("jobs") or {}).get("scan") or {}
backlog = json.load(open("store/iterations/round-2-backlog.json")) if os.path.exists("store/iterations/round-2-backlog.json") else {}
items = backlog.get("items") or []
done = sum(1 for x in items if x.get("status") == "done")
print(f"  task={task_id} status={t.get('status','?')} assignee={t.get('assignee','?')}")
print(f"  gate={'PASS' if gate.get('round2_unlocked') else 'BLOCK'} blockers={gate.get('blockers',[])}")
print(f"  scheduler running={sched.get('running')} scan_last={scan.get('last_run_iso','-')} rc={scan.get('last_rc','-')}")
print(f"  R2 backlog done={done}/{len(items)}")
result = f"store/msg-results/{task_id}.json"
print(f"  msg-results={'Y' if os.path.exists(result) else 'N'}")
PY
  python3 tools/tools/ops/triage-tasks.py 2>/dev/null | grep -E '^(===|  msg-20260616)' | head -20
  [ "$i" -lt "$LOOPS" ] && sleep "$INTERVAL"
done

log "=== watch done ==="
