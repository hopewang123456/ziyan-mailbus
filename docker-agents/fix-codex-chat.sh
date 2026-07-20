#!/bin/bash
# 修复 Web UI 对话：logout + 注入脚本 + 重启 codexapp
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PROJECT="${COMPOSE_PROJECT_NAME:-docker-agents}"
AGENT_DIR="$ROOT/codex-agent"
CATALOG="$AGENT_DIR/deepseek-model-catalog.json"

for name in lingxiao lingjian; do
  ctr="${PROJECT}-${name}-1"
  echo "=== fix $ctr ==="
  docker cp "$AGENT_DIR/start-codex-ui.sh" "${ctr}:/usr/local/bin/start-codex-ui.sh"
  docker cp "$AGENT_DIR/start-codex-web.sh" "${ctr}:/usr/local/bin/start-codex-web.sh"
  docker cp "$AGENT_DIR/entrypoint.sh" "${ctr}:/entrypoint.sh"
  docker exec "${ctr}" chmod +x /usr/local/bin/start-codex-ui.sh /usr/local/bin/start-codex-web.sh /entrypoint.sh
  docker exec "${ctr}" render-codex-config.sh
  docker exec "${ctr}" bash -lc 'codex logout 2>/dev/null || rm -f /home/node/.codex/auth.json; echo OPENAI_API_KEY=${OPENAI_API_KEY:-<unset>}; codex login status 2>&1 | head -2'
  docker exec "${ctr}" pkill -f codexapp 2>/dev/null || true
  sleep 1
  docker exec "${ctr}" start-codex-ui.sh
  docker exec "${ctr}" bash -lc 'timeout 60 codex exec --json --ephemeral --skip-git-repo-check --cd /mailbus/store -s workspace-write -c '"'"'approval_policy="never"'"'"' -m deepseek-v4-flash "Reply exactly: CHAT_OK" 2>&1' | tail -3
done
echo "=== done ==="
