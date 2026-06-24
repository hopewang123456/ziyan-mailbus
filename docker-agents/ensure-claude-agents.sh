#!/bin/bash
# 启动灵云/灵验 Claude Code ttyd Web 终端（宿主机 WSL，非 Docker）
set -uo pipefail

DATA_DIR="${1:-/mnt/e/ai_tools/mail/store}"
SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/tools/start-claude-web.sh"
LOG="${2:-/tmp/start-team.log}"

log() { echo "[ensure-claude] $*"; echo "[ensure-claude] $*" >> "$LOG"; }

if [ ! -x "$SCRIPT" ] && [ ! -f "$SCRIPT" ]; then
  log "ERROR: missing $SCRIPT"
  exit 1
fi

if ! command -v tmux >/dev/null 2>&1; then
  log "WARNING: tmux not installed — sudo apt install tmux"
  exit 0
fi

start_one() {
  local agent="$1" port="$2"
  if bash "$SCRIPT" "$agent" "$port" "$DATA_DIR" >> "$LOG" 2>&1; then
    log "OK $agent ttyd :$port"
    return 0
  fi
  log "WARNING: $agent ttyd :$port failed (see /tmp/claude-web/ttyd-${agent}.log)"
  return 1
}

log "Starting Claude Code web terminals..."

# AgentMemory 探针 + 记忆桥接（best-effort）
AM_URL="${AGENTMEMORY_URL:-http://127.0.0.1:3111}"
if command -v curl >/dev/null 2>&1; then
  if curl -sf --max-time 3 "${AM_URL}/agentmemory/health" >/dev/null 2>&1; then
    log "AgentMemory healthy at ${AM_URL}"
  else
    log "WARNING: AgentMemory unreachable at ${AM_URL} (lingyun 将降级 SQLite 记忆)"
  fi
fi
BRIDGE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/mailbus-memory-bridge.py"
if [ -f "$BRIDGE" ] && command -v python3 >/dev/null 2>&1; then
  python3 "$BRIDGE" sync-claude-agent-context lingyun --data-dir "$DATA_DIR" 2>/dev/null || true
  python3 "$BRIDGE" sync-claude-agent-context lingyan --data-dir "$DATA_DIR" 2>/dev/null || true
fi

rc=0
start_one lingyun 9260 || rc=1
start_one lingyan 9261 || rc=1
exit "$rc"
