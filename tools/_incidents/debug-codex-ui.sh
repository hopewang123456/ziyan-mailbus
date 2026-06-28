#!/bin/bash
set -euo pipefail
C="${1:-docker-agents-lingxiao-1}"

echo "== gateway =="
docker exec "$C" curl -sf http://127.0.0.1:3000/health || echo FAIL_127
docker exec "$C" curl -sf --max-time 3 http://host.docker.internal:3000/health || echo FAIL_host_3000
docker exec "$C" curl -sf --max-time 3 http://host.docker.internal:9220/health || echo FAIL_host_9220

echo "== codexapp pid env =="
pid=$(docker exec "$C" pgrep -f 'codexapp --no-login' | head -1 || true)
if [ -n "$pid" ]; then
  docker exec "$C" bash -lc "tr '\0' '\n' < /proc/$pid/environ | grep -E '^(OPENAI|DEEPSEEK|CODEX_)'" || true
fi

echo "== app-server children =="
docker exec "$C" pgrep -af app-server || echo none

echo "== codex exec test =="
docker exec "$C" bash -lc 'codex exec --json --ephemeral --skip-git-repo-check --cd /mailbus/store -s workspace-write -c '"'"'approval_policy="never"'"'"' -m deepseek-v4-flash "Reply exactly: OK"' 2>&1 | tail -8

echo "== agentmemory =="
docker exec "$C" curl -sf --max-time 5 http://iii-engine:3111/health || echo agentmemory_FAIL

echo "== recent codex-ui log =="
docker exec "$C" tail -30 /tmp/codex-ui/codexapp-lingxiao.log 2>/dev/null || true
