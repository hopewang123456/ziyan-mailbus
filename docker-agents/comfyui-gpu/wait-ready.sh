#!/usr/bin/env bash
set -euo pipefail
for i in $(seq 1 30); do
  if docker top mailbus-comfyui-gpu 2>/dev/null | grep -q 'pip install'; then
    echo "minute=$((i/2)) pip_running"
    sleep 30
  else
    echo pip_finished
    break
  fi
done
docker logs mailbus-comfyui-gpu 2>&1 | tail -25
curl -sS -m 8 http://127.0.0.1:8188/system_stats 2>&1 | head -c 500 || true
