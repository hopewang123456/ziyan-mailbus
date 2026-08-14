#!/bin/bash
# 确保 DeepSeek 网关 + codexapp Web UI 就绪（Browser 启动 / 健康检查用）
set -euo pipefail

CODEX_HOME="${CODEX_HOME:-/home/node/.codex}"
GATEWAY_PORT="${DEEPSEEK_GATEWAY_PORT:-3000}"

render-codex-config.sh

if [ -f "/mailbus/tools/sync_codex_agent_skills.py" ]; then
  CODEX_AGENT="${CODEX_AGENT:-agent-g}" CODEX_HOME="${CODEX_HOME:-/home/node/.codex}" DATA_DIR="/mailbus/store" \
    python3 /mailbus/tools/sync_codex_agent_skills.py || true
fi

rm -f "${CODEX_HOME}/auth.json"

if command -v codex-deepseek-gateway >/dev/null 2>&1; then
  if ! curl -sf "http://127.0.0.1:${GATEWAY_PORT}/health" >/dev/null 2>&1; then
    codex-deepseek-gateway start >/tmp/deepseek-gateway.log 2>&1 &
    for _ in $(seq 1 25); do
      if curl -sf "http://127.0.0.1:${GATEWAY_PORT}/health" >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
  fi
fi

start-codex-ui.sh

if [ "${CODEX_WEB_ENABLED:-0}" = "1" ]; then
  start-codex-web.sh || echo "[ensure-codex-browser] ttyd backup skipped" >&2
fi
