#!/bin/bash
# 下发 mailbus-hardening 任务给灵昭，并触发即时推送
set -euo pipefail

BASE="http://127.0.0.1:9812"
TASK_ID="mailbus-hardening-20260616"
MAIL="/mnt/e/ai_tools/mail"
PLAN="/mnt/e/ai_tools/mail/plans/2026-06-16-mailbus-hardening-inventory.md"

log() { echo "[submit] $*"; }

log "1. create pipeline task"
curl -s -X POST "${BASE}/api/tasks/create" \
  -H "Content-Type: application/json" \
  -d "{
    \"task_id\": \"${TASK_ID}\",
    \"summary\": \"mailbus P0 工作流完善 + skill 专精分配 + 7天归档 + ES日志方案\",
    \"assignee\": \"lingzhao\",
    \"deliverable\": \"plans/mailbus-hardening-plan.md\",
    \"chain\": [\"lingzhao\",\"xiaoqi\",\"lingxiao\",\"lingjian\",\"lingyan\",\"xiaoqi\"]
  }" | head -c 500
echo

MSG="【${TASK_ID}】子言已确认 P0 范围。请阅读：
1) ${PLAN}
2) store/rules/agent-skills-map.md

输出：
- 修复方案与工单拆分（P0 pipeline/skill/归档）
- ES 日志查询看板技术选型建议（Elasticsearch + mailbus 面板接入）
- 7天归档策略与 inbox 减负计划

完成后写 msg-results/${TASK_ID}.json，格式见 role-flow-config.md。"

log "2. instant push to lingzhao"
cd "$MAIL"
python3 -m bus send lingzhao --data-dir store --from mailbus --type task --msg "$MSG"

log "3. trigger scan + pipeline"
python3 -m bus scan --data-dir store 2>&1 | grep -E 'pipeline|推送|task' | tail -10 || true

log "4. task status"
curl -s "${BASE}/api/tasks/${TASK_ID}" 2>/dev/null | python3 -c "
import json,sys
try:
 d=json.load(sys.stdin)
 t=d.get('task',d)
 print('status=', t.get('status'), 'assignee=', t.get('assignee'))
 c=t.get('chain',[])
 if c: print('chain_step=', c[-1].get('to_role'), c[-1].get('to_person'), c[-1].get('status'))
except Exception as e: print('parse err',e)
" 2>/dev/null || echo "(task API pending)"

log "=== submitted ${TASK_ID} ==="
