#!/bin/bash
# 《星际驿站》全员 pipeline — Envelope full_delivery
set -euo pipefail

BASE="http://127.0.0.1:9812"
OLD_ID="game-stellar-20260616"
TASK_ID="game-stellar-20260617"
MAIL="/mnt/e/ai_tools/mail"
RULE="${MAIL}/store/rules/closed-loop-task-design.md"

log() { echo "[game-stellar] $*"; }

log "0. cancel false-success ${OLD_ID}"
python3 <<PY
import json, os
p = "${MAIL}/store/tasks/${OLD_ID}.json"
if os.path.isfile(p):
    t = json.load(open(p, encoding="utf-8"))
    t["status"] = "cancelled"
    t["error"] = {"reason": "false success, superseded by ${TASK_ID}"}
    json.dump(t, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("cancelled", "${OLD_ID}")
PY

rm -f "${MAIL}/store/msg-results/${OLD_ID}.json" 2>/dev/null || true

log "1. create full_delivery ${TASK_ID}"
cd "$MAIL"
python3 tools/task-create-envelope.py \
  --api "${BASE}" \
  --task-id "${TASK_ID}" \
  --intent "星际驿站终端小游戏 — mailbus 12 agent 全员通信验收 (v2)" \
  --task-type full_delivery \
  --tier L \
  --planned-chain "1,3,1,9,8,8,2,5,6,7,11,12"

MSG="【${TASK_ID}】全员 pipeline v2 — 请先阅读 ${RULE}；Step1 写 deliverables 与 step result。"

log "2. push lingzhao"
python3 -m bus send lingzhao --data-dir store --from mailbus --type task --priority urgent --msg "$MSG"

log "3. scan (background)"
flock -n /tmp/mailbus-scan.lock python3 -m bus scan --data-dir store >> /tmp/scan-${TASK_ID}.log 2>&1 &

log "=== submitted ${TASK_ID} ==="
