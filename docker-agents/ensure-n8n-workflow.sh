#!/usr/bin/env bash
# 完整 n8n 发布 workflow 部署：compose up → 导入 → 激活 → 探测
set -euo pipefail
ROOT="/mnt/e/ai_tools/mail"
cd "$ROOT/docker-agents"

docker compose -f docker-compose.n8n.yml up -d

echo "waiting n8n..."
for i in $(seq 1 24); do
  curl -sf --connect-timeout 2 http://127.0.0.1:5678/ >/dev/null 2>&1 && break
  sleep 2
done
curl -sf http://127.0.0.1:5678/ >/dev/null || { echo "n8n not ready"; exit 1; }

CID=$(docker ps -q --filter 'publish=5678' | head -1)
[ -n "$CID" ] || exit 1

# 删除全部同名 workflow，避免重复 webhook 注册
while read -r line; do
  wid="${line%%|*}"
  [ -n "$wid" ] || continue
  docker exec "$CID" n8n delete:workflow --id="$wid" 2>/dev/null || true
done < <(docker exec "$CID" n8n list:workflow 2>/dev/null | grep mailbus-multi-publish || true)

python3 - <<'PY'
import json
src = "/mnt/e/ai_tools/mail/external-tools/n8n/mailbus-multi-publish.workflow.json"
with open(src, encoding="utf-8") as f:
    wf = json.load(f)
wf["active"] = False
with open("/tmp/mailbus-multi-publish-import.json", "w", encoding="utf-8") as f:
    json.dump([wf], f)
PY

docker cp /tmp/mailbus-multi-publish-import.json "$CID:/tmp/import.json"
docker exec "$CID" n8n import:workflow --input=/tmp/import.json

WF_ID=$(docker exec "$CID" n8n list:workflow 2>/dev/null | grep mailbus-multi-publish | head -1 | awk -F'|' '{print $1}' | tr -d '\r\n')
[ -n "$WF_ID" ] || { echo "import failed"; exit 1; }

docker exec "$CID" n8n update:workflow --id="$WF_ID" --active=true
echo "restarting n8n once..."
docker restart "$CID" >/dev/null

for i in $(seq 1 25); do
  curl -sf --connect-timeout 2 http://127.0.0.1:5678/ >/dev/null 2>&1 && break
  sleep 2
done
sleep 10

CODE=$(curl -s -o /tmp/n8n-final.json -w '%{http_code}' \
  -X POST http://127.0.0.1:5678/webhook/mailbus-multi-publish \
  -H 'Content-Type: application/json' \
  -d '{"task_id":"deploy","content_id":"deploy","platforms":["douyin"],"assets":[]}')
echo "webhook HTTP $CODE"
cat /tmp/n8n-final.json 2>/dev/null || true
echo
[ "$CODE" = "200" ] || [ "$CODE" = "201" ]
