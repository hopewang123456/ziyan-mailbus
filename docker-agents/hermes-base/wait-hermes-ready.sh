#!/bin/bash
set -e
C=docker-agents-hermes-1
docker exec -u root $C bash -lc 'if [ -x /ensure-memos.sh ]; then bash /ensure-memos.sh; else true; fi'
echo waiting-dashboards...
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  ok=0
  for p in 9120 9121 9122 9123 9125 9126; do
    if docker exec $C curl -fsS --max-time 1 "http://127.0.0.1:$p/" >/dev/null 2>&1; then ok=$((ok+1)); fi
  done
  v=0
  docker exec $C curl -fsS --max-time 1 http://127.0.0.1:18800/ >/dev/null 2>&1 && v=1 || true
  echo "try $i: dashboards=$ok/6 viewer=$v"
  if [ "$ok" -ge 6 ] && [ "$v" -eq 1 ]; then break; fi
  sleep 5
done
docker exec -u root $C bash -lc '
  export HOME=/home/hermes HERMES_HOME=/home/hermes/.hermes
  hermes memory status | head -20
  ps aux | grep "[h]ermes_cli.main" | wc -l
  for p in 9120 9121 9122 9123 9125 9126; do
    curl -fsS --max-time 1 "http://127.0.0.1:$p/" >/dev/null 2>&1 && echo "dash $p OK" || echo "dash $p down"
  done
  curl -fsS --max-time 2 http://127.0.0.1:18800/ >/dev/null && echo VIEWER_OK || echo VIEWER_DOWN
'
