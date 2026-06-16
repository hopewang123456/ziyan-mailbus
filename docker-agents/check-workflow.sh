#!/bin/bash
curl -s --connect-timeout 5 http://127.0.0.1:9812/api/tasks -o /tmp/check-workflow-tasks.json
python3 <<'PY'
import json
try:
    d = json.load(open("/tmp/check-workflow-tasks.json"))
except Exception as e:
    print("tasks API error:", e)
    raise SystemExit(1)
for t in d.get("tasks", []):
    if "game-lvup" in t.get("task_id", ""):
        print(f"{t['task_id']}\tassignee={t.get('assignee')}\tstatus={t.get('status')}")
PY

echo "--- lingzhao queue head ---"
python3 <<'PY'
import json
for path in ["/mnt/e/ai_tools/mail/store/queue/urgent/lingzhao.json",
             "/mnt/e/ai_tools/mail/store/queue/normal/lingzhao.json"]:
    try:
        d = json.load(open(path))
        msgs = d if isinstance(d, list) else d.get("messages", [])
        print(path.split("/")[-1], "count=", len(msgs))
        for m in msgs[:2]:
            print(" ", m.get("id"), m.get("type"), (m.get("content") or "")[:60])
    except Exception as e:
        print(path, e)
PY

echo "--- game-lvup inbox msg ---"
python3 <<'PY'
import json
d = json.load(open("/mnt/e/ai_tools/mail/store/inbox/lingzhao/inbox.json"))
for m in d.get("messages", []):
    if "game-lvup" in m.get("content", ""):
        print(m.get("id"), "status=", m.get("status"), "pushed=", m.get("pushed_count"))
PY

echo "--- scan cron log tail ---"
tail -3 /mnt/e/ai_tools/mail/store/cron.log 2>/dev/null || echo "(no cron.log yet)"
