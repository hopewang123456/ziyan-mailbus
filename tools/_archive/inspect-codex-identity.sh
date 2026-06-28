#!/bin/bash
set -euo pipefail
C="${1:-docker-agents-lingxiao-1}"
docker exec "$C" bash -lc '
echo "== CODEX_HOME config =="
wc -c /home/node/.codex/config.toml
grep -n "developer_instructions\|personality\|AGENT_ID\|灵霄\|记忆恢复" /home/node/.codex/config.toml | head -15
echo "== project .codex =="
ls -la /mailbus/store/.codex 2>/dev/null || echo none
ls -la /mailbus/store/AGENTS.md 2>/dev/null || echo no AGENTS.md
echo "== codex doctor identity =="
codex debug config 2>&1 | head -30 || true
echo "== codexapp log =="
tail -20 /tmp/codex-ui/codexapp-*.log 2>/dev/null || true
'
