#!/usr/bin/env bash
set -euo pipefail
for i in $(seq 1 30); do
  CODE=$(curl -s -o /tmp/n8n-poll.json -w '%{http_code}' \
    -X POST http://127.0.0.1:5678/webhook/mailbus-multi-publish \
    -H 'Content-Type: application/json' \
    -d '{"task_id":"poll","content_id":"poll","platforms":["douyin"],"assets":[]}' 2>/dev/null || echo 000)
  echo "attempt=$i http=$CODE"
  if [ "$CODE" = "200" ] || [ "$CODE" = "201" ]; then
    cat /tmp/n8n-poll.json
    exit 0
  fi
  sleep 2
done
docker logs "$(docker ps -q --filter publish=5678 | head -1)" 2>&1 | tail -20
exit 1
