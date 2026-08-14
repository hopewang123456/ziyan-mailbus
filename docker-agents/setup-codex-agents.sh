#!/bin/bash
# 构建并重启 Codex 容器（codex-web / codex-review），然后跑冒烟
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
MAILBUS_ROOT="${MAILBUS_ROOT:-$(cd "$ROOT/.." && pwd)}"
cd "$ROOT"
PROJECT="${COMPOSE_PROJECT_NAME:-docker-agents}"
# 现有运行栈多为 docker-agents；.env 里旧 token/网络会与当前栈冲突
if docker ps --format '{{.Names}}' | grep -q '^docker-agents-mailbus-1$'; then
  PROJECT=docker-agents
fi

echo "=== build codex-agent (project=$PROJECT) ==="
docker compose -p "$PROJECT" --env-file .env build codex-web codex-review

echo "=== recreate codex-web codex-review ==="
docker compose -p "$PROJECT" --env-file .env up -d --force-recreate codex-web codex-review

echo "=== wait containers ==="
sleep 12

for svc in codex-web codex-review; do
  cname="${PROJECT}-${svc}-1"
  echo "=== smoke $cname ==="
  python3 "${MAILBUS_ROOT}/tools/smoke-codex-agent.py" --container "$cname" || true
done

echo "=== disk-write probe (codex-web) ==="
docker exec docker-agents-mailbus-1 python3 /mailbus/tools/smoke-agent-disk-write.py \
  --agent agent-g --data-dir /mailbus/store --timeout 600 || true

echo "=== DONE ==="
