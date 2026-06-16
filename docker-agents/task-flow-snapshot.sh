#!/bin/bash
# 快速查看任务流转快照
TASK_ID="${1:-mailbus-hardening-20260616}"
BASE="http://127.0.0.1:9812"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') task flow snapshot ==="

curl -s "${BASE}/api/tasks/${TASK_ID}" -o /tmp/flow-task.json 2>/dev/null
python3 <<PY
import json, os
tid = os.environ.get("TID", "$TASK_ID")
try:
    d = json.load(open("/tmp/flow-task.json"))
    t = d.get("task", d)
except Exception as e:
    print("TASK API error:", e)
    raise SystemExit(1)
print(f"task_id: {t.get('task_id')}")
print(f"status: {t.get('status')}  assignee: {t.get('assignee')}  reminded: {t.get('reminded_count',0)}")
ch = t.get("chain") or []
for i, s in enumerate(ch):
    if isinstance(s, dict):
        print(f"  step{i+1}: {s.get('to_role')}/{s.get('to_person')} status={s.get('status')} started={s.get('started_at','')[:16]}")
    else:
        print(f"  step{i+1}: legacy {s}")
if ch and isinstance(ch[-1], dict) and ch[-1].get("planned_agents"):
    print(f"  planned: {' -> '.join(ch[-1]['planned_agents'])}")
PY

echo "--- msg-results ---"
ls -la "/mnt/e/ai_tools/mail/store/msg-results/${TASK_ID}.json" 2>/dev/null || echo "(no result file yet)"

echo "--- lingzhao inbox msg ---"
python3 <<PY
import json
p="/mnt/e/ai_tools/mail/store/inbox/lingzhao/inbox.json"
d=json.load(open(p))
for m in d.get("messages",[]):
    if "$TASK_ID" in m.get("content",""):
        print(f"  id={m.get('id')} status={m.get('status')} state={m.get('state')} pushed={m.get('pushed_count',0)}")
PY

echo "--- recent cron pipeline ---"
grep -E '\[pipeline\]|hardening' /mnt/e/ai_tools/mail/store/cron.log 2>/dev/null | tail -5 || echo "(no pipeline lines in cron.log)"

echo "--- watch log tail ---"
tail -5 /tmp/pipeline-watch-${TASK_ID}.log 2>/dev/null || echo "(watch not running)"

echo "--- services ---"
curl -s -o /dev/null -w "mailbus=%{http_code} " "$BASE/"
curl -s -o /dev/null -w "lingzhao=%{http_code}\n" "http://127.0.0.1:9120/"
