#!/usr/bin/env bash
set -euo pipefail
echo "=== gateway binary ==="
docker exec docker-agents-codex-web-1 sh -c 'command -v codex-deepseek-gateway; ls -la $(command -v codex-deepseek-gateway); head -60 $(command -v codex-deepseek-gateway) 2>/dev/null || true'
echo "=== gateway src ==="
docker exec docker-agents-codex-web-1 sh -c 'ls /home/node/.codex/deepseek-gateway/src 2>/dev/null; rg -n "listen|HOST|0\.0\.0\.0|127\.0\.0\.1" /home/node/.codex/deepseek-gateway/src 2>/dev/null | head -40 || grep -Rn "listen\|HOST\|0.0.0.0\|127.0.0.1" /home/node/.codex/deepseek-gateway/src 2>/dev/null | head -40'
echo "=== ui logs ==="
docker exec docker-agents-codex-web-1 sh -c 'ls /tmp/codex-ui 2>/dev/null; tail -40 /tmp/codex-ui/codexapp-*.log 2>/dev/null; tail -20 /tmp/codex-ui/codex-ui-proxy-*.log 2>/dev/null'
echo "=== restart ui ==="
docker exec docker-agents-codex-web-1 start-codex-ui.sh || echo "ui fail web"
docker exec docker-agents-codex-review-1 start-codex-ui.sh || echo "ui fail review"
sleep 3
echo "=== probe after ui ==="
for u in http://127.0.0.1:9240/ http://127.0.0.1:9241/ http://127.0.0.1:9220/ http://127.0.0.1:9250/; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 6 "$u" || echo fail)
  echo "$code $u"
done
