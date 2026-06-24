#!/bin/bash
docker exec docker-agents-lingxiao-1 bash -lc '
curl -sf http://127.0.0.1:7681/codex-api/free-mode/status >/dev/null || true
sleep 1
echo "=== processes ==="
ps aux | grep -E "codexapp|app-server" | grep -v grep || true
for pid in $(pgrep -f "codex app-server" 2>/dev/null); do
  echo "--- cmdline pid=$pid ---"
  tr "\0" " " < /proc/$pid/cmdline
  echo
done
'
