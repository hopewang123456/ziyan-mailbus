#!/bin/bash
set -euo pipefail
for ctr in docker-agents-lingxiao-1 docker-agents-lingjian-1; do
  echo "=== install codexapp in $ctr ==="
  docker exec "$ctr" npm install -g codexapp 2>&1 | tail -5
  docker cp /mnt/e/ai_tools/mail/docker-agents/codex-agent/start-codex-ui.sh "$ctr:/usr/local/bin/start-codex-ui.sh"
  docker cp /mnt/e/ai_tools/mail/docker-agents/codex-agent/deepseek-model-aliases.json "$ctr:/tmp/model-aliases.json"
  docker exec "$ctr" chmod +x /usr/local/bin/start-codex-ui.sh
  docker exec "$ctr" bash -lc 'mkdir -p /home/node/.codex/deepseek-gateway/config && cp /tmp/model-aliases.json /home/node/.codex/deepseek-gateway/config/model-aliases.json; rm -f /home/node/.codex/auth.json'
  docker exec "$ctr" pkill -f codexapp 2>/dev/null || true
  sleep 2
  docker exec "$ctr" start-codex-ui.sh
  docker exec "$ctr" start-codex-web.sh 2>/dev/null || true
done
sleep 5
curl -sf -o /dev/null -w '9240=%{http_code} 9250=%{http_code}\n' http://127.0.0.1:9240/ http://127.0.0.1:9250/
curl -sf -o /dev/null -w '9241=%{http_code} 9251=%{http_code}\n' http://127.0.0.1:9241/ http://127.0.0.1:9251/
