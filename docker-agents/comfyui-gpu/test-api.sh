#!/usr/bin/env bash
set -euo pipefail
echo "=== inside container ==="
docker exec mailbus-comfyui-gpu python - <<'PY'
import urllib.request
body = urllib.request.urlopen("http://127.0.0.1:8188/system_stats", timeout=15).read().decode()
print(body[:500])
PY
echo "=== wsl host ==="
curl -sS -m 15 http://127.0.0.1:8188/system_stats | head -c 500 || echo "host curl failed"
