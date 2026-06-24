#!/bin/bash
# 启动 codex app-server + codexapp 可视化 Web UI（projectless 重定向代理 + 工作区锁定）
set -euo pipefail

CODEX_HOME="${CODEX_HOME:-/home/node/.codex}"
UI_PORT="${CODEX_UI_PORT:-7681}"
UI_INTERNAL_PORT="${CODEX_UI_INTERNAL_PORT:-17681}"
AGENT="${CODEX_AGENT:-codex}"
PROJECT_DIR="${CODEX_PROJECT_DIR:-/home/node/agent-workspace/${AGENT}}"
LOG_DIR="/tmp/codex-ui"
PID_FILE="${LOG_DIR}/codexapp-${AGENT}.pid"
PROXY_PID_FILE="${LOG_DIR}/codex-ui-proxy-${AGENT}.pid"
LOG_FILE="${LOG_DIR}/codexapp-${AGENT}.log"
PROXY_LOG="${LOG_DIR}/codex-ui-proxy-${AGENT}.log"

mkdir -p "$LOG_DIR" "$PROJECT_DIR"
render-codex-config.sh

export CODEX_HOME
export CODEX_PROJECT_DIR="$PROJECT_DIR"
export OPENAI_API_KEY="${DEEPSEEK_API_KEY:-${OPENAI_API_KEY:-gateway-local}}"
unset OPENAI_BASE_URL

pkill -f "codex-ui-proxy.mjs" 2>/dev/null || true
pkill -f "codexapp.*--port ${UI_INTERNAL_PORT}" 2>/dev/null || true
pkill -f "codexapp.*--port ${UI_PORT}" 2>/dev/null || true
pkill -f "codex app-server" 2>/dev/null || true
sleep 1

if command -v codexapp >/dev/null 2>&1; then
  CODEXAPP_BIN=(codexapp)
else
  CODEXAPP_BIN=(npx -y codexapp)
fi

nohup "${CODEXAPP_BIN[@]}" \
  --no-login \
  --no-password \
  --no-tunnel \
  --no-open \
  --port "${UI_INTERNAL_PORT}" \
  --sandbox-mode workspace-write \
  --approval-policy never \
  "${PROJECT_DIR}" \
  >"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"

for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:${UI_INTERNAL_PORT}/" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "[codex-ui] codexapp exited early; log tail:" >&2
    tail -40 "$LOG_FILE" >&2 || true
    exit 1
  fi
  sleep 2
done

nohup env CODEX_PROJECT_DIR="$PROJECT_DIR" CODEX_UI_PORT="$UI_PORT" CODEX_UI_INTERNAL_PORT="$UI_INTERNAL_PORT" \
  node /usr/local/share/codex/codex-ui-proxy.mjs \
  >"$PROXY_LOG" 2>&1 &
echo $! >"$PROXY_PID_FILE"

for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${UI_PORT}/" >/dev/null 2>&1; then
    if [ -x /usr/local/bin/pin-codex-workspace.sh ]; then
      /usr/local/bin/pin-codex-workspace.sh || true
    fi
    echo "[codex-ui] ready http://0.0.0.0:${UI_PORT} agent=${AGENT} project=${PROJECT_DIR} (proxy->:${UI_INTERNAL_PORT})" >&2
    exit 0
  fi
  sleep 1
done

echo "[codex-ui] timeout waiting for proxy :${UI_PORT}" >&2
tail -20 "$PROXY_LOG" >&2 || true
tail -20 "$LOG_FILE" >&2 || true
exit 1
