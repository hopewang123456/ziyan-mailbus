#!/usr/bin/env bash
# 启动 n8n（WSL Docker）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker 未安装" >&2
  exit 1
fi

docker compose -f docker-compose.n8n.yml up -d
echo "waiting for n8n (up to 60s) ..."
ready=0
for _ in $(seq 1 12); do
  if curl -sf --connect-timeout 5 http://127.0.0.1:5678/ >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 5
done

echo ""
if [ "$ready" = "1" ]; then
  WSL_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
  echo "n8n UI (WSL): http://127.0.0.1:5678"
  if [ -n "$WSL_IP" ]; then
    echo "n8n UI (Windows, if localhost fails): http://${WSL_IP}:5678"
  fi
  echo "Import workflow: external-tools/n8n/mailbus-multi-publish.workflow.json"
  echo "Deploy: python tools/sync-n8n-url.py  OR  ..\\tools\\setup-n8n.ps1"
else
  echo "WARN: n8n not ready; docker logs $(docker compose -f docker-compose.n8n.yml ps -q n8n 2>/dev/null | head -1)" >&2
fi
