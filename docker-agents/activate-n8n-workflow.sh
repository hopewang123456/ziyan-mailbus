#!/usr/bin/env bash
set -euo pipefail
CID=$(docker ps -q --filter 'publish=5678' | head -1)
[ -n "$CID" ] || exit 1

WF_ID=$(docker exec "$CID" n8n list:workflow 2>/dev/null | grep mailbus-multi-publish | head -1 | awk -F'|' '{print $1}' | tr -d '\r\n')
[ -n "$WF_ID" ] || { echo "workflow not found"; exit 1; }

docker exec "$CID" n8n update:workflow --id="$WF_ID" --active=true
echo "restarting n8n once..."
docker restart "$CID" >/dev/null

for i in $(seq 1 20); do
  if curl -sf --connect-timeout 2 http://127.0.0.1:5678/ >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

CODE=$(curl -s -o /tmp/n8n-live-probe.json -w '%{http_code}' \
  -X POST http://127.0.0.1:5678/webhook/mailbus-multi-publish \
  -H 'Content-Type: application/json' \
  -d '{"task_id":"live","content_id":"live","platforms":["douyin"],"assets":[]}')
echo "webhook HTTP $CODE"
head -c 300 /tmp/n8n-live-probe.json
echo
[ "$CODE" = "200" ] || [ "$CODE" = "201" ]
