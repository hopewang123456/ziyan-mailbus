#!/bin/bash
# 下发 mailbus-hardening 任务（A2A Envelope）
set -euo pipefail

BASE="http://127.0.0.1:9812"
TASK_ID="mailbus-hardening-20260616"
MAIL="/mnt/e/ai_tools/mail"
PLAN="/mnt/e/ai_tools/mail/plans/2026-06-16-mailbus-hardening-inventory.md"

log() { echo "[submit] $*"; }

log "1. create pipeline task (Envelope)"
cd "$MAIL"
python3 tools/task-create-envelope.py \
  --api "${BASE}" \
  --task-id "${TASK_ID}" \
  --intent "mailbus P0 工作流完善 + skill 专精分配 + 7天归档 + ES日志方案" \
  --task-type feature \
  --tier M \
  --planned-chain "1,9,8,5,6,12"

MSG="【${TASK_ID}】子言已确认 P0 范围。请阅读：
1) ${PLAN}
2) store/rules/agent-skills-map.md

输出修复方案与工单拆分；完成后写 msg-results/${TASK_ID}/step-s1.json（见 pipeline-agent-paths.md）。"

log "2. push to lingzhao"
python3 -m bus send lingzhao --data-dir store --from mailbus --type task --msg "$MSG"

log "3. scan"
python3 -m bus scan --data-dir store 2>&1 | tail -5 || true

log "=== submitted ${TASK_ID} ==="
