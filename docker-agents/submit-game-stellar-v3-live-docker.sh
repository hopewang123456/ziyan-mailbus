#!/bin/bash
# v3 LIVE 验收 — 容器内 Envelope 创建
set -euo pipefail

BASE="http://127.0.0.1:9812"
TASK_ID="${1:-game-stellar-v3-20260618}"
STORE="/mailbus/store"

log() { echo "[v3-live] $*"; }

log "0. repair stuck"
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

log "2. create task (Envelope) if missing"
if [ ! -f "${STORE}/tasks/${TASK_ID}.json" ]; then
  python3 /mailbus/tools/task-create-envelope.py \
    --api "${BASE}" \
    --task-id "${TASK_ID}" \
    --intent "星际驿站 v3 LIVE — 全员 agent 真实写 msg-results 验收" \
    --task-type full_delivery \
    --tier L \
    --planned-chain "1,3,1,9,8,8,2,5,6,7,11,12"
else
  echo '{"status":"skip","reason":"task exists"}'
fi

log "3. push step1"
python3 /mailbus/tools/pipeline-push-step1.py --data-dir store --task-id "${TASK_ID}" --agent lingzhao

log "=== v3-live ready ${TASK_ID} ==="
