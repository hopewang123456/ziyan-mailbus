#!/bin/bash
set -e
C=docker-agents-hermes-1
docker ps --filter name=$C --format '{{.Names}} {{.Status}}'
echo ---
docker inspect $C --format '{{range .Mounts}}{{if eq .Destination "/home/hermes/.hermes"}}{{.Source}}{{end}}{{end}}'
echo ---
docker exec -u root $C bash -lc '
  export HOME=/home/hermes HERMES_HOME=/home/hermes/.hermes
  hermes memory status
  echo ---
  ps aux | grep "[h]ermes_cli.main" | wc -l
  ps aux | grep "[h]ermes_cli.main" | sed "s/  */ /g" | cut -d" " -f11- | head -10
  echo ---
  test -f /home/hermes/.hermes/memos-plugin/data/memos.db && echo MEMOS_DB_OK
  curl -fsS --max-time 2 http://127.0.0.1:18800/ >/dev/null && echo VIEWER_OK || echo VIEWER_DOWN
  # dashboards ports
  for p in 9120 9121 9122 9123 9125 9126; do
    if curl -fsS --max-time 1 "http://127.0.0.1:$p/" >/dev/null 2>&1; then echo "dash $p OK"; else echo "dash $p down"; fi
  done
'
