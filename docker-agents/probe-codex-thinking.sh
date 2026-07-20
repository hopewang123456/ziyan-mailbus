#!/bin/bash
# 发送测试消息后抓取 codexapp / app-server 日志
set -euo pipefail
c="${1:-docker-agents-lingxiao-1}"
docker exec "$c" bash -lc '
echo "=== time ==="
date
echo "=== codex login ==="
codex login status 2>&1 | head -3
echo "=== gateway ==="
curl -sf http://127.0.0.1:3000/health; echo
echo "=== app-server test (15s timeout) ==="
timeout 15 codex exec --json --skip-git-repo-check --cd /mailbus/store \
  -s workspace-write -c '"'"'approval_policy="never"'"'"' \
  -m deepseek-v4-flash "你好，只回复：OK" 2>&1 | tail -6 || echo TIMEOUT_OR_FAIL
echo "=== codexapp log tail ==="
tail -30 /tmp/codex-ui/codexapp-*.log 2>/dev/null || true
echo "=== ps app-server ==="
ps aux | grep -E "app-server|codex" | grep -v grep || true
'
