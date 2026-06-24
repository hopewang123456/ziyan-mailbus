#!/bin/bash
# 重新渲染 config（含记忆）并重启 codexapp
set -euo pipefail
for ctr in docker-agents-lingxiao-1 docker-agents-lingjian-1; do
  echo "== $ctr =="
  docker cp /mnt/e/ai_tools/mail/docker-agents/codex-agent/render-codex-config.sh "$ctr:/usr/local/bin/render-codex-config.sh"
  docker exec "$ctr" bash -lc 'render-codex-config.sh; pkill -f codexapp || true; sleep 2; start-codex-ui.sh'
  docker exec "$ctr" bash -lc "grep -E 'AGENT_ID|记忆恢复|本地快照' /home/node/.codex/config.toml | head -6"
done
