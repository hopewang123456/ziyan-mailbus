#!/bin/bash
# OpenCode agent：加载 Hermes 同源 .env + 等待 AgentMemory
set -euo pipefail

if [ -f /run/hermes/.env ]; then
  set -a
  # shellcheck disable=SC1091
  . /run/hermes/.env
  set +a
fi

export OPENAI_API_KEY="${OPENAI_API_KEY:-${DEEPSEEK_API_KEY:-}}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://api.deepseek.com/v1}"

WAIT_AM="/mailbus/docker-agents/codex-agent/wait-agentmemory.sh"
if [ -f "$WAIT_AM" ]; then
  bash "$WAIT_AM" || true
fi

if [ "${MEMORY_BRIDGE_AGENTMEMORY:-0}" = "1" ] && [ -f /mailbus/store/config.json ]; then
  if command -v python3 >/dev/null 2>&1 && [ -f /mailbus/tools/mailbus-memory-bridge.py ]; then
    python3 /mailbus/tools/mailbus-memory-bridge.py sync-claude-agent-context agent-i \
      --data-dir /mailbus/store 2>/dev/null || true
  fi
fi

if [ -f /mailbus/tools/sync-all-agent-layers.py ]; then
  python3 /mailbus/tools/sync-all-agent-layers.py --data-dir /mailbus/store --skip-hermes --skip-codex --skip-claude || true
fi

exec "$@"
