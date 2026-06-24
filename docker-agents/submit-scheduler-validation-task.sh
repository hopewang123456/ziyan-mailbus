#!/bin/bash
# 下发 mailbus-scheduler-validation 主任务（A2A Envelope）
set -euo pipefail

BASE="http://127.0.0.1:9812"
TASK_ID="mailbus-scheduler-validation-20260616"
MAIL="/mnt/e/ai_tools/mail"

log() { echo "[submit-scheduler] $*"; }

log "1. create task ${TASK_ID}"
cd "$MAIL"
python3 tools/task-create-envelope.py \
  --api "${BASE}" \
  --task-id "${TASK_ID}" \
  --intent "内置 SchedulerHub 验证：scan/bridge/patrol + agent 推送链路" \
  --task-type ops \
  --tier M \
  --planned-chain "1,9,8,5,6,12"

MSG="【${TASK_ID}】验证 mailbus 内置调度器与各 agent 执行链路。见 store/config.json scheduler.jobs；写 per-step msg-results。"

log "2. push to lingzhao"
python3 -m bus send lingzhao --data-dir store --from mailbus --type task --priority urgent --msg "$MSG"

log "3. primary_task_id"
python3 tools/set-primary-task.py "${TASK_ID}" || true

log "=== submitted ${TASK_ID} ==="
