#!/bin/bash
# v3 LIVE 验收 — 在 mailbus 容器内执行（基础设施修复版）
set -euo pipefail

BASE="http://127.0.0.1:9812"
TASK_ID="${1:-game-stellar-20260618}"
MAIL="/mailbus"
STORE="/mailbus/store"
FULL_CHAIN='["lingzhao","lingxi","lingzhao","xiaoqi","lingxiao","dali","lingjin","lingjian","lingyan","lingxun","yige","xiaoqi"]'

log() { echo "[v3-live] $*"; }

log "0. repair stuck state"
python3 /mailbus/tools/repair-pipeline-stuck.py --data-dir store --task-id "${TASK_ID}" --fix || true

log "1. iteration-state -> ${TASK_ID}"
python3 <<PY
import json, os
p = "${STORE}/iterations/iteration-state.json"
st = json.load(open(p, encoding="utf-8")) if os.path.isfile(p) else {}
st["primary_task_id"] = "${TASK_ID}"
g = st.get("gate") or {}
g["primary_task_id"] = "${TASK_ID}"
g["primary_status"] = "running"
g["blockers"] = []
st["gate"] = g
st["round1"] = {"phase": "execution", "status": "running"}
json.dump(st, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("ok")
PY

mkdir -p "${STORE}/deliverables/${TASK_ID}"
rm -f "${STORE}/msg-results/${TASK_ID}.json"

log "2. create or refresh task"
python3 <<PY
import json, urllib.request, os
tid = "${TASK_ID}"
base = "${BASE}"
payload = {
    "task_id": tid,
    "summary": "星际驿站 v3 LIVE — 全员 agent 真实写 msg-results 验收",
    "assignee": "lingzhao",
    "deliverable": f"deliverables/{tid}/",
    "chain": json.loads('${FULL_CHAIN}'),
}
# 若已存在则跳过 create
if not os.path.isfile(f"/mailbus/store/tasks/{tid}.json"):
    req = urllib.request.Request(
        f"{base}/api/tasks/create",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        print(resp.read().decode())
else:
    print(json.dumps({"status": "skip", "reason": "task exists"}))
PY

log "3. Step1 结构化工单 + API 推送（禁止 bus send，避免重复 tracker）"
python3 /mailbus/tools/_archive/pipeline-push-step1.py --data-dir store --task-id "${TASK_ID}" --agent lingzhao

log "4. scan"
cd "$MAIL"
python3 -m bus scan --data-dir store 2>&1 | tail -25

log "5. lingzhao inbox"
python3 <<PY
import json
from lib.models import Inbox
from lib.utils import json_read
d = json_read("/mailbus/store/inbox/lingzhao/inbox.json", {})
inbox = Inbox.from_dict(d)
for m in reversed(inbox.messages[-5:]):
    mid = inbox.msg_field(m, "id", "")
    if "${TASK_ID}" not in inbox.msg_field(m, "content", "") and inbox.msg_field(m, "task_id", "") != "${TASK_ID}":
        continue
    st = inbox.msg_field(m, "state", "") or inbox.msg_field(m, "status", "")
    print(f"  {mid} task_id={inbox.msg_field(m,'task_id','')} state={st}")
PY

log "=== done ${TASK_ID} ==="
log "验收: test -f ${STORE}/msg-results/${TASK_ID}.json"
