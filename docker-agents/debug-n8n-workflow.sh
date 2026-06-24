#!/usr/bin/env bash
set -euo pipefail
CID=$(docker ps -q --filter 'publish=5678' | head -1)
[ -n "$CID" ] || { echo no_cid; exit 1; }
for i in $(seq 1 15); do curl -sf http://127.0.0.1:5678/ >/dev/null && break; sleep 2; done
curl -sf http://127.0.0.1:5678/ >/dev/null || { echo n8n_down; exit 1; }

echo "=== export workflow ==="
docker exec "$CID" n8n export:workflow --id=IXRp0awzeqMtWP8x --output=/tmp/exp.json 2>&1 || true
docker exec "$CID" cat /tmp/exp.json 2>/dev/null | head -c 1500 || true
echo
echo "=== active workflows rest ==="
curl -s http://127.0.0.1:5678/rest/active-workflows 2>/dev/null | head -c 500 || echo rest_fail
echo
echo "=== webhook from inside container ==="
docker exec "$CID" wget -qO- --post-data='{"task_id":"in","content_id":"in","platforms":["douyin"],"assets":[]}' --header='Content-Type: application/json' http://127.0.0.1:5678/webhook/mailbus-multi-publish 2>&1 | head -c 300 || true
