#!/bin/bash
# mailbus 工作流冒烟：Envelope 创建 + 推送 inbox
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${SCRIPT_DIR}/lib/api-url.sh"

BASE="$MAILBUS_API_BASE"
TS=$(date +%Y%m%d-%H%M%S)
TASK_ID="game-lvup-${TS}"
MAIL="/mnt/e/ai_tools/mail"

log() { echo "[workflow] $*"; }

log "=== workflow test ${TASK_ID} ==="
log "1. create task (Envelope)"
cd "$MAIL"
python3 tools/tools/ops/task-create-envelope.py \
  --api "${BASE}" \
  --task-id "${TASK_ID}" \
  --intent "打怪升级小游戏 MVP" \
  --task-type feature \
  --tier M \
  --planned-chain "1,9,8,8,5,6"

log "2. push to lingzhao"
python3 -m bus send lingzhao --data-dir store --from mailbus --type task \
  --msg "【${TASK_ID}】请输出打怪升级小游戏 MVP 方案要点（3条以内），完成后写 msg-results。"

log "3. list tasks"
curl -s "${BASE}/api/tasks" | python3 -c "import sys,json; d=json.load(sys.stdin); t=[x for x in d.get('tasks',[]) if x.get('task_id','').startswith('game-lvup')]; print('tasks', len(t)); print(t[-1].get('task_id') if t else 'none')" 2>/dev/null || true

log "=== workflow smoke done ==="
