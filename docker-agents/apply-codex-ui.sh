#!/bin/bash
# 热更新灵霄/灵鉴：codexapp 主 UI + projectless 代理 + ttyd 备用
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
PROJECT="${COMPOSE_PROJECT_NAME:-docker-agents}"
AGENT_DIR="$ROOT/codex-agent"

BIN_SCRIPTS=(
  start-codex-ui.sh
  start-codex-web.sh
  ensure-codex-browser.sh
  render-codex-config.sh
  sync-codex-home-mirror.sh
  pin-codex-workspace.sh
  wait-agentmemory.sh
)

echo "=== recreate with new port mappings ==="
docker compose -p "$PROJECT" up -d --force-recreate --no-build lingxiao lingjian

echo "=== wait startup ==="
sleep 15

for name in lingxiao lingjian; do
  ctr="${PROJECT}-${name}-1"
  echo "=== inject scripts + start services in $ctr ==="
  for s in "${BIN_SCRIPTS[@]}"; do
    docker cp "$AGENT_DIR/$s" "${ctr}:/usr/local/bin/$s"
    docker exec "${ctr}" chmod +x "/usr/local/bin/$s"
  done
  docker cp "$AGENT_DIR/entrypoint.sh" "${ctr}:/entrypoint.sh"
  docker exec "${ctr}" chmod +x /entrypoint.sh
  docker cp "$AGENT_DIR/codex-ui-proxy.mjs" "${ctr}:/usr/local/share/codex/codex-ui-proxy.mjs"
  docker exec "${ctr}" ensure-codex-browser.sh || true
done

sleep 8
docker ps --format 'table {{.Names}}\t{{.Ports}}' | grep ling || true

echo "=== smoke ==="
python3 /mnt/e/ai_tools/mail/tools/smoke-codex-agent.py --container "${PROJECT}-lingxiao-1" || true
python3 /mnt/e/ai_tools/mail/tools/smoke-codex-agent.py --container "${PROJECT}-lingjian-1" || true

echo "=== DONE ==="
