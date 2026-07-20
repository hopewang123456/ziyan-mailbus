#!/bin/bash
# 《信使迷宫》全员 pipeline live 验收
set -euo pipefail

BASE="http://127.0.0.1:9814"
TASK_ID="game-courier-20260625"
MAIL="/mnt/e/ai_tools/mail"
RULE="${MAIL}/store/rules/closed-loop-task-design.md"

log() { echo "[game-courier] $*"; }

log "0. pre-flight"
python3 "${MAIL}/tools/_archive/check-preflight.py" --data-dir "${MAIL}/store" --api "${BASE}" || true

log "1. create full_delivery ${TASK_ID}"
cd "$MAIL"
python3 tools/_archive/task-create-envelope.py \
  --api "${BASE}" \
  --task-id "${TASK_ID}" \
  --intent "信使迷宫终端小游戏 — mailbus 12 agent 全员 live 验收" \
  --task-type full_delivery \
  --tier L \
  --planned-chain "1,3,1,9,8,8,2,5,6,7,11,12"

MSG="【${TASK_ID}】请阅读 ${RULE}；Step1 输出方案 3 条要点 + deliverables/${TASK_ID}/ 目录规划，写 msg-results（含 pipeline_step/agent）。"

log "2. push lingzhao"
python3 -m bus send lingzhao --data-dir store --from ziyan --type task --priority urgent --msg "$MSG"

log "3. trigger scan"
flock -n /tmp/mailbus-scan.lock python3 -m bus scan --data-dir store >> "/tmp/scan-${TASK_ID}.log" 2>&1 || true

log "=== submitted ${TASK_ID} ==="
log "watch: python3 tools/watch-task-pipeline.py --task-id ${TASK_ID} --interval 30 --rounds 480"
