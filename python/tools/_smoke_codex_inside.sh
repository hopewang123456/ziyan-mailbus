#!/usr/bin/env bash
set -euo pipefail
echo "=== processes ==="
docker exec docker-agents-codex-web-1 sh -c 'ps aux | head -40'
echo "=== curl inside ==="
docker exec docker-agents-codex-web-1 sh -c '
for u in http://127.0.0.1:7681/ http://0.0.0.0:7681/ http://127.0.0.1:7682/ http://127.0.0.1:3000/ http://127.0.0.1:17681/; do
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time 4 "$u" || echo fail)
  echo "$code $u"
done
'
echo "=== host via docker publish ==="
for u in http://127.0.0.1:9220/ http://127.0.0.1:9240/ http://127.0.0.1:9250/; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 --max-time 4 "$u" || echo fail)
  echo "$code $u"
done
echo "=== review container ==="
docker exec docker-agents-codex-review-1 sh -c '
for u in http://127.0.0.1:7681/ http://127.0.0.1:3000/; do
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time 4 "$u" || echo fail)
  echo "$code $u"
done
'
echo "=== windows-side note via wsl curl publish 9241 ==="
curl -s -o /dev/null -w '%{http_code}' --connect-timeout 2 --max-time 4 http://127.0.0.1:9241/ || echo fail
echo " 9241"
