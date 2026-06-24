#!/bin/bash
# 部署项目级 AGENTS.md + .codex 并重启 Web UI
set -euo pipefail
for ctr in docker-agents-lingxiao-1 docker-agents-lingjian-1; do
  echo "== $ctr =="
  docker cp /mnt/e/ai_tools/mail/docker-agents/codex-agent/render-codex-config.sh "$ctr:/usr/local/bin/"
  docker cp /mnt/e/ai_tools/mail/docker-agents/codex-agent/start-codex-ui.sh "$ctr:/usr/local/bin/"
  docker exec "$ctr" chmod +x /usr/local/bin/render-codex-config.sh /usr/local/bin/start-codex-ui.sh
  docker exec "$ctr" start-codex-ui.sh
  agent=$(docker exec "$ctr" printenv CODEX_AGENT)
  docker exec "$ctr" ls -la "/home/node/agent-workspace/${agent}/AGENTS.md"
  docker exec "$ctr" head -3 "/home/node/agent-workspace/${agent}/AGENTS.md"
done
