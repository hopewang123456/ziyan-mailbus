#!/bin/bash
# 全 agent 配置 + 挂载 + Hermes profile 启动探针
set -euo pipefail
MAIL="/mnt/e/ai_tools/mail"
TIMEOUT="${HERMES_PROBE_TIMEOUT:-45}"

echo "=== 1. config 校验 ==="
docker exec docker-agents-mailbus-1 python3 /mailbus/tools/ops/tools/ops/validate-agents-config.py \
  --data-dir /mailbus/store

echo "=== 2. store 挂载 ==="
bash "$MAIL/docker-agents/verify-agent-store-mount.sh"

echo "=== 3. Hermes profile CLI 启动探针（各 profile 仅验证不报 Unknown skill） ==="
docker exec docker-agents-mailbus-1 python3 /mailbus/tools/ops/tools/ops/smoke-hermes-profiles.py \
  --timeout "$TIMEOUT"

echo "=== 4. Codex 容器探针（lingxiao / lingjian）==="
for svc in lingxiao lingjian; do
  cname="docker-agents-${svc}-1"
  if docker ps --format '{{.Names}}' | grep -qx "$cname"; then
    docker exec "$cname" codex --version
  else
    echo "WARN: $cname not running (skip codex probe)"
  fi
done

echo "=== ALL AGENTS VALIDATION PASS ==="
