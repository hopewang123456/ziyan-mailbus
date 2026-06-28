#!/bin/bash
# 持续监控 pipeline 任务链 + 服务健康（可 cron 或后台跑）
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${SCRIPT_DIR}/lib/api-url.sh"

TASK_ID="${1:-mailbus-hardening-20260616}"
INTERVAL="${2:-60}"
MAX_ROUNDS="${3:-9999}"
BASE="$MAILBUS_API_BASE"
LOG="/tmp/pipeline-watch-${TASK_ID}.log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }

round=0
last_chain=""
while [ "$round" -lt "$MAX_ROUNDS" ]; do
  round=$((round + 1))
  log "--- round $round task=$TASK_ID ---"

  # 服务健康
  code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 "$BASE/" 2>/dev/null || echo "000")
  if [ "$code" != "200" ]; then
    log "ALERT mailbus HTTP $code — 尝试 scan 恢复"
    cd /mnt/e/ai_tools/mail && flock -n /tmp/mailbus-scan.lock python3 -m bus scan --data-dir store >> "$LOG" 2>&1 || true
  fi

  # 任务链状态
  curl -s "${BASE}/api/tasks/${TASK_ID}" -o /tmp/pw-task.json 2>/dev/null || true
  chain_line=$(python3 <<PY 2>/dev/null || echo "parse_error"
import json
try:
    d=json.load(open("/tmp/pw-task.json"))
    t=d.get("task",d)
    st=t.get("status","?")
    asn=t.get("assignee","?")
    ch=t.get("chain",[])
    if ch and isinstance(ch[-1],dict):
        cur=ch[-1]
        line=f"status={st} assignee={asn} step={cur.get('to_role')}/{cur.get('to_person')} step_status={cur.get('status')}"
    else:
        line=f"status={st} assignee={asn} chain_len={len(ch)}"
    print(line)
    if st in ("success","failed","cancelled"):
        raise SystemExit(0)
except SystemExit:
    raise
except Exception as e:
    print(f"error={e}")
PY
)

  if [ "$chain_line" != "$last_chain" ]; then
    log "CHANGE $chain_line"
    last_chain="$chain_line"
  else
    log "OK $chain_line"
  fi

  if echo "$chain_line" | grep -qE 'status=success|status=failed'; then
    log "TASK TERMINAL — stopping watch"
    break
  fi

  # 卡住检测：running 超过 3 轮无变化则强制 scan
  if [ "$round" -gt 3 ] && [ "$chain_line" = "$last_chain" ]; then
    :
  fi
  cd /mnt/e/ai_tools/mail && flock -n /tmp/mailbus-scan.lock python3 -m bus scan --data-dir store >> "$LOG" 2>&1 || true

  sleep "$INTERVAL"
done

log "watch ended"
