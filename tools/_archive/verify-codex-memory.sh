#!/bin/bash
set -euo pipefail
for c in docker-agents-lingxiao-1 docker-agents-lingjian-1; do
  echo "== $c =="
  docker exec "$c" bash -lc 'bash /mailbus/tools/sync-codex-agent-skills.sh "${CODEX_AGENT}" "${CODEX_HOME}" /mailbus/store' 2>&1 | tail -1 || true
  docker exec "$c" start-codex-ui.sh 2>&1 | tail -1
  docker exec "$c" bash -lc 'test -f "/home/node/.codex/skills/${CODEX_AGENT}-memory/output.md" && echo "memory skill ok" || echo "WARN: missing memory skill"'
  docker exec "$c" bash -lc 'grep "AGENT_ID" /home/node/.codex/config.toml || true'
  docker exec "$c" bash -lc 'grep -c "记忆恢复" /home/node/.codex/config.toml || true'
  docker exec "$c" bash -lc 'grep -c "session 快照" /home/node/.codex/config.toml || true'
  docker exec "$c" bash -lc 'curl -sf -o /dev/null -w "ttyd=%{http_code}\n" "http://127.0.0.1:${CODEX_WEB_PORT:-7682}/" || echo ttyd=fail'
done
