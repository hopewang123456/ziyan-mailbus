#!/bin/bash
# 监控工作流任务链流转（轮询直到超时或完成）
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${SCRIPT_DIR}/lib/api-url.sh"

TASK_PREFIX="${1:-game-lvup}"
MAX_WAIT="${2:-300}"
INTERVAL="${3:-15}"
BASE="$MAILBUS_API_BASE"

log() { echo "[workflow-watch] $(date '+%H:%M:%S') $*"; }

get_task() {
  curl -s "${BASE}/api/tasks" 2>/dev/null | python3 -c "
import json, sys
prefix = sys.argv[1]
d = json.load(sys.stdin)
tasks = [t for t in d.get('tasks', []) if t.get('task_id', '').startswith(prefix) and t.get('chain')]
tasks.sort(key=lambda x: x.get('created_at', ''), reverse=True)
if tasks:
    t = tasks[0]
    print(t['task_id'], t.get('assignee'), t.get('status'), '|'.join(t.get('chain') or []))
" "$TASK_PREFIX" 2>/dev/null
}

log "监控任务前缀: $TASK_PREFIX (最长 ${MAX_WAIT}s, 间隔 ${INTERVAL}s)"
last=""
elapsed=0
while [ "$elapsed" -lt "$MAX_WAIT" ]; do
  line=$(get_task || echo "")
  if [ -n "$line" ] && [ "$line" != "$last" ]; then
    log "状态变化: $line"
    last="$line"
    status=$(echo "$line" | awk '{print $3}')
    if [ "$status" = "done" ] || [ "$status" = "completed" ]; then
      log "任务完成"
      exit 0
    fi
  fi
  # 手动触发 scan 加速（cron 可能刚装）
  if [ $((elapsed % 60)) -eq 0 ] && [ "$elapsed" -gt 0 ]; then
    cd /mnt/e/ai_tools/mail && flock -n /tmp/mailbus-scan.lock python3 -m bus scan --data-dir store >> /tmp/workflow-scan.log 2>&1 &
    log "触发 scan (background)"
  fi
  sleep "$INTERVAL"
  elapsed=$((elapsed + INTERVAL))
done

log "超时，最终状态: ${last:-unknown}"
exit 1
