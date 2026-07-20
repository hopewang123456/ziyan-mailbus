#!/bin/bash
# mailbus 全流程回归：pipeline E2E + monitor-regression
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/mailbus-env.sh
. "${SCRIPT_DIR}/lib/mailbus-env.sh"
# shellcheck source=lib/api-url.sh
. "${SCRIPT_DIR}/lib/api-url.sh"

COMPOSE="${SCRIPT_DIR}"
MAIL="${MAILBUS_ROOT}"
LOG="${COMPOSE}/mailbus-pipeline-e2e.log"

log() { echo "[pipeline-e2e] $*" | tee -a "$LOG"; }

log "=== mailbus pipeline E2E $(date '+%Y-%m-%d %H:%M:%S') ==="

# 1. 确保 mailbus 容器运行
if ! docker ps --format '{{.Names}}' | grep -q '^docker-agents-mailbus-1$'; then
  log "starting mailbus..."
  cd "$COMPOSE" && docker compose up -d mailbus
  sleep 8
fi

# 2. 内置 pipeline 回归（scheduler → msg-results → audit → gate → Round2）
log "--- pipeline-e2e-regression ---"
cd "$MAIL"
if docker exec docker-agents-mailbus-1 python3 /mailbus/tools/_archive/pipeline-e2e-regression.py \
    --data-dir /mailbus/store --url http://127.0.0.1:${MAILBUS_API_PORT} 2>&1 | tee -a "$LOG"; then
  log "pipeline e2e: PASS"
else
  log "pipeline e2e: FAIL (retry from host)"
  python3 tools/_archive/pipeline-e2e-regression.py --data-dir store || exit 1
fi

# 3. triage 快照
log "--- triage ---"
python3 tools/_archive/triage-tasks.py --data-dir store 2>&1 | tee -a "$LOG"
log "--- reconcile audits ---"
docker exec docker-agents-mailbus-1 python3 /mailbus/tools/_archive/flush-pending-audits.py --data-dir /mailbus/store 2>&1 | tee -a "$LOG" || true

# 4. monitor-regression
log "--- monitor-regression ---"
bash "$COMPOSE/monitor-regression.sh" 2>&1 | tee -a "$LOG"

# 5. task-flow 快照
PRIMARY="$(python3 -c "import json; print(json.load(open('store/iterations/iteration-state.json')).get('primary_task_id','mailbus-scheduler-validation-20260616'))")"
bash "$COMPOSE/task-flow-snapshot.sh" "$PRIMARY" 2>&1 | tee -a "$LOG"

# 5. Round2 dispatch + 闭环
log "--- Round2 dispatch ---"
bash "$COMPOSE/run-mailbus-iteration.sh" 2 dispatch-r2 2>&1 | tee -a "$LOG" || true

log "--- Round2 complete ---"
cd "$MAIL"
python3 tools/_archive/complete-round2-regression.py --data-dir store 2>&1 | tee -a "$LOG"

log "--- final pipeline-e2e verify ---"
docker exec docker-agents-mailbus-1 python3 /mailbus/tools/_archive/pipeline-e2e-regression.py \
    --data-dir /mailbus/store --url http://127.0.0.1:${MAILBUS_API_PORT} 2>&1 | tee -a "$LOG" || \
  python3 tools/_archive/pipeline-e2e-regression.py --data-dir store 2>&1 | tee -a "$LOG"

log "=== pipeline E2E complete ==="
