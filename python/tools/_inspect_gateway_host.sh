#!/usr/bin/env bash
set -euo pipefail
GW=/usr/local/lib/node_modules/@galaxy-yearn/codex-deepseek-gateway
echo "=== listen/host in package ==="
docker exec docker-agents-codex-web-1 sh -c "grep -Rn \"listen\\|host\\|HOST\\|0.0.0.0\\|127.0.0.1\" $GW/src/server.js $GW/src/config.js $GW/src/runtime.js 2>/dev/null | head -60"
echo "=== env ==="
docker exec docker-agents-codex-web-1 sh -c 'env | grep -iE "GATEWAY|HOST|LISTEN|BIND" || true'
echo "=== try restart with host env guesses ==="
# Inspect help
docker exec docker-agents-codex-web-1 sh -c 'codex-deepseek-gateway --help 2>&1 | head -80'
