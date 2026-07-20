#!/bin/bash
# 后台挂 game-stellar（或任意 task）pipeline 监控
set -euo pipefail

TASK_ID="${1:-game-stellar-20260616}"
INTERVAL="${2:-30}"
MAIL="/mnt/e/ai_tools/mail"
LOG="/tmp/pipeline-watch-${TASK_ID}.log"
PIDFILE="/tmp/pipeline-watch-${TASK_ID}.pid"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "watch 已在运行 PID=$(cat "$PIDFILE") log=$LOG"
  exit 0
fi

nohup python3 "$MAIL/tools/watch-task-pipeline.py" \
  --task-id "$TASK_ID" \
  --data-dir "$MAIL/store" \
  --interval "$INTERVAL" \
  > "/tmp/watch-${TASK_ID}-stdout.log" 2>&1 &
echo $! > "$PIDFILE"
echo "started PID=$(cat "$PIDFILE")"
echo "  log: $LOG"
echo "  tail: tail -f $LOG"
echo "  snap: bash $MAIL/docker-agents/task-flow-snapshot.sh $TASK_ID"
