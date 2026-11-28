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

exec "$@"
