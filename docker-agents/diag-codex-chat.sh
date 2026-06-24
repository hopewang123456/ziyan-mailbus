#!/bin/bash
set -euo pipefail
c="${1:-docker-agents-lingxiao-1}"
docker exec "$c" bash -lc '
echo "=== login status ==="
codex login status 2>&1 || true
echo "=== catalog line 15-25 ==="
sed -n "15,25p" /home/node/.codex/deepseek-model-catalog.json
echo "=== exec test ==="
codex exec --json --ephemeral --skip-git-repo-check --cd /mailbus/store \
  -s workspace-write -c '"'"'approval_policy="never"'"'"' \
  -m deepseek-v4-flash "Reply exactly: OK" 2>&1 | tail -8
echo "=== codexapp log ==="
tail -50 /tmp/codex-ui/codexapp-*.log 2>/dev/null || true
echo "=== processes ==="
ps aux | grep -E "app-server|codexapp|codex " | grep -v grep || true
'
