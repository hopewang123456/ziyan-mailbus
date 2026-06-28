#!/bin/bash
# 快速验证 UI 路径：app-server + gateway + MCP
set -euo pipefail
C="${1:-docker-agents-lingxiao-1}"

echo "== test gateway via responses =="
docker exec "$C" bash -lc 'curl -sf -X POST http://127.0.0.1:3000/v1/responses \
  -H "Authorization: Bearer ${DEEPSEEK_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"deepseek-chat\",\"input\":\"say hi\",\"stream\":false}" 2>&1 | head -c 400'
echo

echo "== test wrong host.docker.internal:3000 =="
docker exec "$C" curl -sf --max-time 3 http://host.docker.internal:3000/health || echo FAIL

echo "== restart codexapp with fixed env =="
docker exec "$C" bash -lc '
  pkill -f codexapp || true
  sleep 1
  export OPENAI_API_KEY="${DEEPSEEK_API_KEY}"
  unset OPENAI_BASE_URL CODEX_OPENAI_BASE_URL
  render-codex-config.sh
  start-codex-ui.sh
'

echo "== codexapp env after restart =="
pid=$(docker exec "$C" pgrep -f "codexapp --no-login" | head -1)
docker exec "$C" bash -lc "tr '\0' '\n' < /proc/$pid/environ | grep -E '^(OPENAI|DEEPSEEK|CODEX_OPENAI)' || true"
