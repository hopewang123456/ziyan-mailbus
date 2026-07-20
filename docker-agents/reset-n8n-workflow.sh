#!/usr/bin/env bash
# 重置 n8n 数据卷并部署单一 mailbus-multi-publish workflow
set -euo pipefail
ROOT="/mnt/e/ai_tools/mail"
cd "$ROOT/docker-agents"

echo "[reset-n8n] stopping and removing n8n volume..."
docker compose -f docker-compose.n8n.yml down -v

echo "[reset-n8n] starting fresh n8n..."
docker compose -f docker-compose.n8n.yml up -d

for i in $(seq 1 30); do
  curl -sf --connect-timeout 2 http://127.0.0.1:5678/ >/dev/null 2>&1 && break
  sleep 2
done
curl -sf http://127.0.0.1:5678/ >/dev/null || { echo "n8n not ready"; exit 1; }

CID=$(docker ps -q --filter 'publish=5678' | head -1)

python3 - <<'PY'
import json
src = "/mnt/e/ai_tools/mail/external-tools/n8n/mailbus-multi-publish.workflow.json"
with open(src, encoding="utf-8") as f:
    wf = json.load(f)
wf["active"] = False
with open("/tmp/mb-import.json", "w", encoding="utf-8") as f:
    json.dump([wf], f)
PY

docker cp /tmp/mb-import.json "$CID:/tmp/import.json"
docker exec "$CID" n8n import:workflow --input=/tmp/import.json

WF_ID=$(docker exec "$CID" n8n list:workflow 2>/dev/null | grep mailbus-multi-publish | head -1 | awk -F'|' '{print $1}' | tr -d '\r\n')
echo "WF_ID=$WF_ID"
[ -n "$WF_ID" ] || exit 1

docker exec "$CID" n8n update:workflow --id="$WF_ID" --active=true
docker restart "$CID" >/dev/null

for i in $(seq 1 25); do
  curl -sf http://127.0.0.1:5678/ >/dev/null 2>&1 && break
  sleep 2
done
sleep 10

CODE=$(curl -s -o /tmp/out.json -w '%{http_code}' \
  -X POST http://127.0.0.1:5678/webhook/mailbus-multi-publish \
  -H 'Content-Type: application/json' \
  -d '{"task_id":"fresh","content_id":"fresh","platforms":["douyin"],"assets":[]}')
echo "webhook HTTP $CODE"
cat /tmp/out.json
echo
docker exec "$CID" n8n list:workflow 2>/dev/null || true
[ "$CODE" = "200" ] || [ "$CODE" = "201" ]
