#!/usr/bin/env bash
set -euo pipefail
for u in \
  http://127.0.0.1:9120/ \
  http://127.0.0.1:9121/ \
  http://127.0.0.1:18789/ \
  http://127.0.0.1:18790/ \
  http://127.0.0.1:9240/ \
  http://127.0.0.1:9220/ \
  http://127.0.0.1:9814/api/status
do
  code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 6 "$u" || echo fail)
  echo "$code $u"
done
echo "--- docker ---"
docker ps --format '{{.Names}} {{.Status}}' | head -20
echo "--- cli ---"
command -v hermes || true
command -v openclaw || true
command -v opencode || true
command -v codex || true
