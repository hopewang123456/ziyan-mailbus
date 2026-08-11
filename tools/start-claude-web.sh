#!/bin/bash
# WSL 内启动 Claude Code ttyd Web 终端（DeepSeek/MiniMax 经 claude CLI / PowerShell 桥接）
set -euo pipefail

AGENT="${1:-}"
WEB_PORT="${2:-9260}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ -f "${ROOT}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/.env" 2>/dev/null || true
  set +a
fi
DEFAULT_DATA="${MAILBUS_DATA:-${MAILBUS_ROOT:+${MAILBUS_ROOT}/store}}"
DATA_DIR="${3:-${DEFAULT_DATA:-${ROOT}/store}}"

if [ -z "$AGENT" ]; then
  echo "Usage: start-claude-web.sh <agent> [web_port] [data_dir]" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SYNC_PY="${ROOT}/tools/sync-claude-agent-context.py"
TMUX_SESSION="claude-${AGENT}"
LOG_DIR="/tmp/claude-web"
PID_FILE="${LOG_DIR}/ttyd-${AGENT}.pid"

TTYD_BIN="${TTYD_BIN:-}"
if [ -z "$TTYD_BIN" ] || [ ! -x "$TTYD_BIN" ]; then
  if command -v ttyd >/dev/null 2>&1; then
    TTYD_BIN="$(command -v ttyd)"
  elif [ -x "${ROOT}/docker-agents/codex-agent/bin/ttyd.x86_64" ]; then
    TTYD_BIN="${ROOT}/docker-agents/codex-agent/bin/ttyd.x86_64"
  elif [ -x "${ROOT}/tools/bin/ttyd.x86_64" ]; then
    TTYD_BIN="${ROOT}/tools/bin/ttyd.x86_64"
  else
    echo "[claude-web] ttyd not found. Install: sudo apt install ttyd" >&2
    echo "[claude-web] or use bundled: ${ROOT}/docker-agents/codex-agent/bin/ttyd.x86_64" >&2
    exit 1
  fi
fi

if ! command -v tmux >/dev/null 2>&1; then
  echo "[claude-web] tmux not installed (sudo apt install tmux)" >&2
  exit 1
fi

mkdir -p "$LOG_DIR"

_session_ok() {
  tmux has-session -t "${TMUX_SESSION}" 2>/dev/null
}

_stop_ttyd() {
  if [ -f "$PID_FILE" ]; then
    local old_pid
    old_pid=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
      kill "$old_pid" 2>/dev/null || true
      sleep 1
    fi
    rm -f "$PID_FILE"
  fi
  fuser -k "${WEB_PORT}/tcp" 2>/dev/null || true
  sleep 0.5
}

if curl -sf "http://127.0.0.1:${WEB_PORT}/" >/dev/null 2>&1 && _session_ok; then
  echo "[claude-web] already listening on :${WEB_PORT} agent=${AGENT} session=${TMUX_SESSION}" >&2
  exit 0
fi

if curl -sf "http://127.0.0.1:${WEB_PORT}/" >/dev/null 2>&1 && ! _session_ok; then
  echo "[claude-web] ttyd up but tmux session missing — restarting :${WEB_PORT}" >&2
  _stop_ttyd
fi

if [ -f "$SYNC_PY" ]; then
  python3 "$SYNC_PY" "$AGENT" --data-dir "$DATA_DIR" || true
fi

START_INNER=$(python3 -c "
import sys
sys.path.insert(0, '${ROOT}')
from lib.adapters.frameworks.claude_launch import build_interactive_shell_inner
print(build_interactive_shell_inner('${AGENT}', '${DATA_DIR}'))
")

AGENT_TITLE=$(python3 -c "
import json,sys
sys.path.insert(0, '${ROOT}')
from lib.infra.utils import json_read
cfg=json_read('${DATA_DIR}/config.json',{})
a=cfg.get('agents',{}).get('${AGENT}',{})
print((a.get('name') or '${AGENT}') + ' (${AGENT})')
" 2>/dev/null || echo "${AGENT}")

START_SCRIPT="${LOG_DIR}/start-${AGENT}.sh"
cat > "$START_SCRIPT" <<SCRIPT
#!/bin/bash
set +e
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
while true; do
  ${START_INNER}
  ec=\$?
  echo
  echo "[claude-web] shell exited (\$ec). Retry in 3s — Ctrl+C to stop."
  sleep 3
done
SCRIPT
chmod +x "$START_SCRIPT"

if tmux has-session -t "${TMUX_SESSION}" 2>/dev/null; then
  tmux kill-session -t "${TMUX_SESSION}" 2>/dev/null || true
  sleep 0.5
fi
tmux new-session -d -s "${TMUX_SESSION}" "$START_SCRIPT"

_stop_ttyd

nohup "$TTYD_BIN" -p "${WEB_PORT}" -i 0.0.0.0 -W -t disableReuse=true -t "titleFixed=${AGENT_TITLE}" \
  tmux attach -t "${TMUX_SESSION}" \
  >"${LOG_DIR}/ttyd-${AGENT}.log" 2>&1 &
echo $! > "$PID_FILE"

for _ in $(seq 1 25); do
  if curl -sf "http://127.0.0.1:${WEB_PORT}/" >/dev/null 2>&1 && _session_ok; then
    echo "[claude-web] ready http://127.0.0.1:${WEB_PORT} agent=${AGENT} session=${TMUX_SESSION}" >&2
    exit 0
  fi
  sleep 1
done

echo "[claude-web] failed to start on :${WEB_PORT} (see ${LOG_DIR}/ttyd-${AGENT}.log)" >&2
tail -20 "${LOG_DIR}/ttyd-${AGENT}.log" 2>/dev/null || true
exit 1
