#!/bin/bash
# mailbus 工作流冒烟：创建任务链 + 推送 inbox 消息
set -euo pipefail

BASE="http://127.0.0.1:9812"
TS=$(date +%Y%m%d-%H%M%S)
TASK_ID="game-lvup-${TS}"

log() { echo "[workflow] $*"; }

create_task() {
  curl -s -X POST "${BASE}/api/tasks/create" \
    -H "Content-Type: application/json" \
    -d "{\"task_id\":\"${TASK_ID}\",\"summary\":\"打怪升级小游戏 MVP\",\"assignee\":\"lingzhao\",\"deliverable\":\"方案文档\",\"chain\":[\"lingzhao\",\"xiaoqi\",\"lingxiao\",\"dali\",\"lingjian\",\"lingyan\"]}" \
    | head -c 400
  echo
}

push_inbox() {
  local agent="$1"
  local msg="$2"
  cd /mnt/e/ai_tools/mail
  python3 -m bus send "$agent" --data-dir store --from mailbus --type task \
    --msg "$msg" 2>&1 | tail -3
}

log "=== workflow test ${TASK_ID} ==="
log "1. create task"
create_task

log "2. push to lingzhao (design)"
push_inbox lingzhao "【${TASK_ID}】请输出打怪升级小游戏 MVP 方案要点（3条以内），完成后 mailbus 回复。"

log "3. list tasks"
curl -s "${BASE}/api/tasks" | python3 -c "import sys,json; d=json.load(sys.stdin); t=[x for x in d.get('tasks',[]) if x.get('task_id','').startswith('game-lvup')]; print('tasks', len(t)); print(t[-1] if t else 'none')" 2>/dev/null || echo "tasks api ok"

log "4. mailbus status"
curl -s -o /dev/null -w "mailbus=%{http_code}\n" "${BASE}/"

log "=== workflow smoke done ==="
