#!/bin/bash
# 《星际驿站》全员 pipeline — 作废假 success 任务后重发
set -euo pipefail

BASE="http://127.0.0.1:9812"
OLD_ID="game-stellar-20260616"
TASK_ID="game-stellar-20260617"
MAIL="/mnt/e/ai_tools/mail"
RULE="${MAIL}/rules/closed-loop-task-design.md"

log() { echo "[game-stellar] $*"; }

log "0. cancel false-success task ${OLD_ID}"
python3 <<PY
import json, os
p = "${MAIL}/store/tasks/${OLD_ID}.json"
if os.path.isfile(p):
    t = json.load(open(p, encoding="utf-8"))
    t["status"] = "cancelled"
    t["error"] = {"reason": "false success (2/12), superseded by ${TASK_ID}"}
    json.dump(t, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("cancelled", "${OLD_ID}")
PY

rm -f "${MAIL}/store/msg-results/${OLD_ID}.json" 2>/dev/null || true

FULL_CHAIN='["lingzhao","lingxi","lingzhao","xiaoqi","lingxiao","dali","lingjin","lingjian","lingyan","lingxun","yige","xiaoqi"]'

log "1. create 12-step pipeline task ${TASK_ID}"
curl -s -X POST "${BASE}/api/tasks/create" \
  -H "Content-Type: application/json" \
  -d "{
    \"task_id\": \"${TASK_ID}\",
    \"summary\": \"星际驿站终端小游戏 — mailbus 10 agent 全员通信验收 (v2)\",
    \"assignee\": \"lingzhao\",
    \"deliverable\": \"deliverables/${TASK_ID}/\",
    \"chain\": ${FULL_CHAIN}
  }" | head -c 600
echo

MSG="【${TASK_ID}】全员 pipeline 验收 v2 — 《星际驿站 Stellar Mail Hub》

请先阅读：${RULE} 与 skill closed-loop-task-design

Step1 交付：
- deliverables/${TASK_ID}/scheme.md
- msg-results/${TASK_ID}.json 必填：task_id, agent=lingzhao, pipeline_step=1, timestamp

若需 UI 调研：conclusion=need_research（planned 仍会自动派灵犀，勿手写跳步）"

log "2. urgent push to lingzhao"
cd "$MAIL"
python3 -m bus send lingzhao --data-dir store --from mailbus --type task --priority urgent --msg "$MSG"

log "3. async scan (non-blocking)"
flock -n /tmp/mailbus-scan.lock python3 -m bus scan --data-dir store >> /tmp/scan-${TASK_ID}.log 2>&1 &

log "4. task snapshot"
curl -s "${BASE}/api/tasks" 2>/dev/null | python3 -c "
import json,sys
tid='${TASK_ID}'
d=json.load(sys.stdin)
tasks=[t for t in d.get('tasks',[]) if t.get('task_id')==tid]
if tasks:
 t=tasks[0]; ch=t.get('chain') or []
 print('status=', t.get('status'))
 print('planned=', len(ch[0].get('planned_agents') or []), 'agents')
" 2>/dev/null || true

log "5. restart watch"
bash "${MAIL}/docker-agents/start-pipeline-watch.sh" "${TASK_ID}" 30

log "=== submitted ${TASK_ID} ==="
