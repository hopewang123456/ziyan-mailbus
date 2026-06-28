#!/bin/bash
# 验证 codexapp Web UI 使用 DeepSeek 自定义网关而非 OpenCode Zen
set -euo pipefail
ctr="${1:-docker-agents-lingxiao-1}"
docker exec "$ctr" bash -lc '
set -e
echo "=== webui-custom-providers.json ==="
cat /home/node/.codex/webui-custom-providers.json
echo
echo "=== workspace roots ==="
cat /home/node/.codex/.codex-global-state.json
echo
echo "=== free-mode status ==="
curl -sf http://127.0.0.1:7681/codex-api/free-mode/status 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "(codexapp not ready)"
echo "=== restart codexapp to reload app-server ==="
start-codex-ui.sh
sleep 3
# 触发 app-server 启动
curl -sf http://127.0.0.1:7681/codex-api/free-mode/status >/dev/null || true
sleep 2
echo "=== app-server process args ==="
ps aux | grep "codex app-server" | grep -v grep || echo "(app-server not spawned yet — open Web UI and send a message)"
'
