#!/bin/bash
# 灵霄 Cline：优先加载 Hermes 同源 .env，保证 DeepSeek key 与团队一致
set -euo pipefail

if [ -f /run/hermes/.env ]; then
  set -a
  # shellcheck disable=SC1091
  . /run/hermes/.env
  set +a
fi

export OPENAI_API_KEY="${OPENAI_API_KEY:-${DEEPSEEK_API_KEY:-}}"
export OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://api.deepseek.com/v1}"

exec "$@"
