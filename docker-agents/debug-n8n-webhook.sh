#!/usr/bin/env bash
set -euo pipefail
BASE="http://127.0.0.1:5678"
PAYLOAD='{"task_id":"v","content_id":"v","platforms":["douyin"],"assets":[]}'

curl -sf "$BASE/" >/dev/null || { echo "n8n down"; exit 1; }

for path in \
  "/webhook/mailbus-multi-publish" \
  "/webhook-test/mailbus-multi-publish" \
  "/webhook/v1/mailbus-multi-publish"; do
  CODE=$(curl -s -o /tmp/v.json -w '%{http_code}' -X POST "$BASE$path" \
    -H 'Content-Type: application/json' -d "$PAYLOAD")
  echo "$path -> $CODE $(head -c 120 /tmp/v.json)"
done

docker logs "$(docker ps -q --filter publish=5678 | head -1)" 2>&1 | grep -i webhook | tail -10 || true
