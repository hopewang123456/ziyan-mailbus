#!/bin/bash
# 停止灵云/灵验 Claude Code ttyd + tmux 会话
set -uo pipefail

LOG_DIR="/tmp/claude-web"

for agent in lingyun lingyan; do
  pid_file="${LOG_DIR}/ttyd-${agent}.pid"
  if [ -f "$pid_file" ]; then
    pid=$(cat "$pid_file" 2>/dev/null || true)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$pid_file"
  fi
  tmux kill-session -t "claude-${agent}" 2>/dev/null || true
done

fuser -k 9260/tcp 9261/tcp 2>/dev/null || true
echo "[stop-claude] Claude ttyd sessions stopped"
