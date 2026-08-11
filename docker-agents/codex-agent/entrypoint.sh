#!/bin/bash
# Codex agent：DeepSeek 网关 + AgentMemory MCP + 人设 config
set -euo pipefail

if [ -f /run/hermes/.env ]; then
  set -a
  # shellcheck disable=SC1091
  . /run/hermes/.env
  set +a
fi

export OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://api.deepseek.com/v1}"
export CODEX_HOME="${CODEX_HOME:-/home/node/.codex}"
export AGENTMEMORY_URL="${AGENTMEMORY_URL:-http://iii-engine:3111}"
export DEEPSEEK_GATEWAY_PORT="${DEEPSEEK_GATEWAY_PORT:-3000}"

mkdir -p "$CODEX_HOME"

# DeepSeek Responses 网关（Codex 仅支持 responses wire）
GW_DIR="$CODEX_HOME/deepseek-gateway"
mkdir -p "$GW_DIR/config"
ALIASES_SRC="/usr/local/share/codex/deepseek-model-aliases.json"
if [ -f "$ALIASES_SRC" ]; then
  cp "$ALIASES_SRC" "$GW_DIR/config/model-aliases.json"
fi
if [ -n "${DEEPSEEK_API_KEY:-}" ]; then
  cat > "$GW_DIR/config/gateway.local.json" <<EOF
{"upstreamApiKey":"${DEEPSEEK_API_KEY}"}
EOF
fi

if command -v codex-deepseek-gateway >/dev/null 2>&1; then
  codex-deepseek-gateway install >/dev/null 2>&1 || true
  if ! curl -sf "http://127.0.0.1:${DEEPSEEK_GATEWAY_PORT}/health" >/dev/null 2>&1; then
    codex-deepseek-gateway start >/tmp/deepseek-gateway.log 2>&1 &
    for _ in $(seq 1 30); do
      if curl -sf "http://127.0.0.1:${DEEPSEEK_GATEWAY_PORT}/health" >/dev/null 2>&1; then
        echo "[codex-agent] deepseek gateway ready on :${DEEPSEEK_GATEWAY_PORT}" >&2
        break
      fi
      sleep 1
    done
  fi
fi

if [ "${FORCE_RENDER_CODEX_CONFIG:-0}" = "1" ]; then
  render-codex-config.sh || echo "[codex-agent] render-codex-config failed, continuing without it" >&2
else
  render-codex-config.sh 2>/dev/null || echo "[codex-agent] codex config render skipped (already exists or FORCE_RENDER_CODEX_CONFIG=0)" >&2
fi

if [ -x /usr/local/bin/sync-codex-home-mirror.sh ]; then
  /usr/local/bin/sync-codex-home-mirror.sh
fi

# 勿用 codex login --with-api-key：会把 Web UI 锁到 OpenAI 默认模型 big-pickle，导致一直 thinking
if [ -f "$CODEX_HOME/auth.json" ]; then
  codex logout >/dev/null 2>&1 || rm -f "$CODEX_HOME/auth.json"
fi

if [ "${CODEX_UI_ENABLED:-1}" = "1" ]; then
  start-codex-ui.sh || echo "[codex-agent] codex-ui start skipped" >&2
fi
if [ "${CODEX_WEB_ENABLED:-0}" = "1" ]; then
  start-codex-web.sh || echo "[codex-agent] codex-web (ttyd backup) start skipped" >&2
fi

exec "$@"
