#!/bin/bash
# 下发 mailbus-scheduler-validation 主任务 — 验证内置 SchedulerHub + agent 链路
set -euo pipefail

BASE="http://127.0.0.1:9812"
TASK_ID="mailbus-scheduler-validation-20260616"
MAIL="/mnt/e/ai_tools/mail"
DATE="$(date +%Y%m%d)"

log() { echo "[submit-scheduler] $*"; }

log "1. create pipeline task ${TASK_ID}"
curl -s -X POST "${BASE}/api/tasks/create" \
  -H "Content-Type: application/json" \
  -d "{
    \"task_id\": \"${TASK_ID}\",
    \"summary\": \"内置 SchedulerHub 验证：scan/bridge/patrol + WSL crontab 已清理 + agent 推送链路\",
    \"assignee\": \"lingzhao\",
    \"deliverable\": \"msg-results/${TASK_ID}.json\",
    \"chain\": [\"lingzhao\",\"xiaoqi\",\"lingxiao\",\"lingjian\",\"lingyan\",\"xiaoqi\"]
  }" | head -c 600
echo

MSG="【${TASK_ID}】【Round1 自优化测试】验证 mailbus 内置调度器与各 agent 执行链路。

必读：
- store/config.json → scheduler.jobs
- store/scheduler.log / store/iterations/iteration-protocol.md（store/rules/iteration-protocol.md）
- GET http://127.0.0.1:9812/api/status → scheduler.running=true

验收：
1. scheduler scan 每 60s 自动跑（无需 WSL crontab）
2. 各 agent inbox 能收到 task 并完成 ack → processing → msg-results
3. 写 msg-results/${TASK_ID}.json（含 next_role），推进 pipeline

完成后通知灵鉴审计。禁止手工 crontab。"

log "2. push task to lingzhao"
cd "$MAIL"
python3 -m bus send lingzhao --data-dir store --from mailbus --type task --priority urgent --msg "$MSG"

log "3. update iteration-state primary_task_id"
python3 tools/set-primary-task.py "${TASK_ID}" || docker exec docker-agents-mailbus-1 python3 /mailbus/tools/set-primary-task.py "${TASK_ID}" || true

log "4. trigger scan (scheduler may also run)"
python3 -m bus scan --data-dir store 2>&1 | grep -E '推送|pipeline|scheduler|发现' | tail -8 || true

log "=== submitted ${TASK_ID} — 等待 pipeline + 灵鉴 audit 后 Round2 解锁 ==="
