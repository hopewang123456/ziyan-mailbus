#!/bin/bash
# 等待 AgentMemory HTTP 路由就绪（iii-engine 冷启动 + worker 注册）
set -euo pipefail

AM_URL="${AGENTMEMORY_URL:-http://iii-engine:3111}"
MAX_WAIT="${AGENTMEMORY_WAIT_SEC:-60}"

if ! command -v curl >/dev/null 2>&1; then
  exit 0
fi

for i in $(seq 1 "$MAX_WAIT"); do
  if curl -sf --max-time 3 "${AM_URL}/agentmemory/health" >/dev/null 2>&1; then
    echo "[wait-agentmemory] ready after ${i}s (${AM_URL})" >&2
    exit 0
  fi
  sleep 1
done

echo "[wait-agentmemory] timeout after ${MAX_WAIT}s (${AM_URL}) — continuing without remote memory" >&2
exit 0
