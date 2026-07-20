#!/bin/bash
# 热修复：DeepSeek 网关别名 + 重启 UI，让 Web 对话走本地网关
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
AGENT_DIR="$ROOT/codex-agent"
PROJECT="${COMPOSE_PROJECT_NAME:-docker-agents}"

for name in lingxiao lingjian; do
  ctr="${PROJECT}-${name}-1"
  echo "=== gateway-ui fix $ctr ==="
  docker cp "$AGENT_DIR/deepseek-model-aliases.json" "${ctr}:/usr/local/share/codex/deepseek-model-aliases.json"
  docker cp "$AGENT_DIR/start-codex-ui.sh" "${ctr}:/usr/local/bin/start-codex-ui.sh"
  docker cp "$AGENT_DIR/entrypoint.sh" "${ctr}:/entrypoint.sh"
  docker exec "${ctr}" chmod +x /usr/local/bin/start-codex-ui.sh /entrypoint.sh
  docker exec "${ctr}" bash -lc '
    GW=/home/node/.codex/deepseek-gateway
    mkdir -p "$GW/config"
    cp /usr/local/share/codex/deepseek-model-aliases.json "$GW/config/model-aliases.json"
    pkill -f "deepseek-gateway/src/server.js" 2>/dev/null || true
    sleep 1
    codex-deepseek-gateway start >/tmp/deepseek-gateway.log 2>&1 &
    for _ in $(seq 1 20); do curl -sf http://127.0.0.1:3000/health >/dev/null && break; sleep 1; done
    render-codex-config.sh
    codex logout 2>/dev/null || rm -f /home/node/.codex/auth.json
    export OPENAI_API_KEY=gateway-local
    export OPENAI_BASE_URL=http://127.0.0.1:3000/v1
    curl -sf -m 30 http://127.0.0.1:3000/v1/responses \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer gateway-local" \
      -d '"'"'{"model":"big-pickle","input":"Say OK"}'"'"' | head -c 200; echo
    pkill -f codexapp 2>/dev/null || true
    sleep 1
    start-codex-ui.sh
  '
done

sleep 3
curl -sf -o /dev/null -w '9240=%{http_code} 9241=%{http_code}\n' http://127.0.0.1:9240/ http://127.0.0.1:9241/
echo "=== done ==="
