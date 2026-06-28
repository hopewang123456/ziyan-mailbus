#!/bin/bash
set -euo pipefail
C="${1:-docker-agents-lingxiao-1}"
for base in "http://iii-engine:3111" "http://agentmemory:3111" "http://iii-engine:3112"; do
  for p in /agentmemory/livez /agentmemory/health /agentmemory/memories; do
    code=$(docker exec "$C" curl -sf -o /dev/null -w '%{http_code}' --max-time 5 "${base}${p}" 2>/dev/null || echo ERR)
    echo "${base}${p} -> ${code}"
  done
done
docker exec "$C" ls -la /home/node/.codex/skills/lingxiao-memory/output.md 2>/dev/null || echo "no output.md in container path"
docker exec "$C" head -5 /home/node/.codex/skills/lingxiao-memory/output.md 2>/dev/null || true
