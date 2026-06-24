#!/bin/bash
docker exec docker-agents-lingxiao-1 bash -lc '
export CODEX_HOME=/home/node/.codex
echo "=== login status ==="
codex login status 2>&1
echo "=== auth files ==="
ls -la /home/node/.codex/*.json 2>/dev/null || ls -la /home/node/.codex/ | head -20
echo "=== app-server ws test ==="
pkill -f "ws://127.0.0.1:4501" 2>/dev/null || true
sleep 1
nohup codex app-server --listen ws://127.0.0.1:4501 > /tmp/app-server-test.log 2>&1 &
for i in $(seq 1 15); do
  if grep -q "listening\|ready\|4501" /tmp/app-server-test.log 2>/dev/null; then break; fi
  sleep 1
done
tail -20 /tmp/app-server-test.log
echo "=== ps ==="
ps aux | grep app-server | grep -v grep || true
pkill -f "ws://127.0.0.1:4501" 2>/dev/null || true
'
