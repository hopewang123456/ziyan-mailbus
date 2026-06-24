#!/bin/bash
docker exec docker-agents-lingxiao-1 bash -lc '
echo "=== config.toml model lines ==="
grep model /home/node/.codex/config.toml | head -10
echo "=== catalog slugs ==="
python3 -c "import json; print([m[\"slug\"] for m in json.load(open(\"/home/node/.codex/deepseek-model-catalog.json\"))[\"models\"]])"
echo "=== try app-server briefly ==="
timeout 5 codex app-server --listen 127.0.0.1:4501 2>&1 | head -15 &
sleep 3
curl -sf http://127.0.0.1:4501/ 2>&1 | head -c 200; echo
pkill -f "4501" 2>/dev/null || true
'
