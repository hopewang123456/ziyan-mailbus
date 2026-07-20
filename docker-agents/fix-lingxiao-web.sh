#!/bin/bash
set -euo pipefail
ctr=docker-agents-lingxiao-1
docker exec "$ctr" bash -lc 'mkdir -p /home/node/.codex/deepseek-gateway/config && cp /tmp/model-aliases.json /home/node/.codex/deepseek-gateway/config/model-aliases.json'
docker exec "$ctr" bash -lc 'pkill -f deepseek-gateway/src/server.js || true; sleep 1; codex-deepseek-gateway start >/tmp/gw.log 2>&1 & sleep 4; curl -sf http://127.0.0.1:3000/health; echo'
docker exec "$ctr" bash -lc 'curl -sf -m 40 http://127.0.0.1:3000/v1/responses -H "Content-Type: application/json" -H "Authorization: Bearer gateway-local" -d '"'"'{"model":"big-pickle","input":"Say OK"}'"'"' | head -c 300; echo'
docker cp /mnt/e/ai_tools/mail/docker-agents/codex-agent/start-codex-ui.sh "$ctr:/usr/local/bin/start-codex-ui.sh"
docker exec "$ctr" chmod +x /usr/local/bin/start-codex-ui.sh
docker exec "$ctr" bash -lc 'rm -f /home/node/.codex/auth.json; pkill -f codexapp || true; sleep 1; start-codex-ui.sh'
curl -sf -o /dev/null -w '9240=%{http_code}\n' http://127.0.0.1:9240/
