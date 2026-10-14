#!/usr/bin/env bash
set -euo pipefail
# Restart deepseek gateway with HOST=0.0.0.0 inside both codex containers
for ctn in docker-agents-codex-web-1 docker-agents-codex-review-1; do
  echo "=== $ctn ==="
  docker exec "$ctn" sh -c '
    export HOST=0.0.0.0
    export DEEPSEEK_GATEWAY_PORT="${DEEPSEEK_GATEWAY_PORT:-3000}"
    codex-deepseek-gateway stop --force >/dev/null 2>&1 || true
    sleep 1
    nohup env HOST=0.0.0.0 DEEPSEEK_GATEWAY_PORT="${DEEPSEEK_GATEWAY_PORT:-3000}" \
      codex-deepseek-gateway start >/tmp/deepseek-gateway.log 2>&1 &
    for i in $(seq 1 20); do
      if curl -sf "http://127.0.0.1:${DEEPSEEK_GATEWAY_PORT:-3000}/health" >/dev/null 2>&1; then
        echo "gateway health ok"
        break
      fi
      sleep 1
    done
    # show listen
    python3 - <<"PY"
import socket
s=socket.socket();
import os
port=int(os.environ.get("DEEPSEEK_GATEWAY_PORT","3000"))
# parse /proc/net/tcp for bind
print("probe localhost", end=" ")
import urllib.request
try:
  urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
  print("ok")
except Exception as e:
  print(e)
PY
  ' || echo "fail $ctn"
done
echo "=== host publish ==="
for u in http://127.0.0.1:9220/health http://127.0.0.1:9221/health http://127.0.0.1:9240/ http://127.0.0.1:9250/ http://127.0.0.1:9260/ http://127.0.0.1:9261/; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 5 "$u" || echo fail)
  echo "$code $u"
done
