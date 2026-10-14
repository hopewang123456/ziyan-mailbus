#!/usr/bin/env bash
set -euo pipefail
sleep 5
for u in \
  http://127.0.0.1:9220/ \
  http://127.0.0.1:9240/ \
  http://127.0.0.1:9250/ \
  http://127.0.0.1:18790/ \
  http://127.0.0.1:9120/ \
  http://127.0.0.1:18789/
do
  code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 8 "$u" || echo fail)
  echo "$code $u"
done
echo "--- codex logs ---"
docker logs docker-agents-codex-web-1 2>&1 | tail -50
echo "--- openclaw 18790 ---"
docker logs docker-agents-openclaw-1 2>&1 | tail -30
echo "--- listen inside codex ---"
docker exec docker-agents-codex-web-1 sh -c "ss -lntp 2>/dev/null || netstat -lntp 2>/dev/null || cat /proc/net/tcp | head"
echo "--- listen openclaw ---"
docker exec docker-agents-openclaw-1 sh -c "ss -lntp 2>/dev/null || netstat -lntp 2>/dev/null || true" | head -30
