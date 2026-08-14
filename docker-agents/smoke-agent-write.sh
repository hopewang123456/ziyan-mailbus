#!/bin/bash
# 最短 agent 落盘探针（WSL 入口）
set -euo pipefail
AGENT="${1:-agent-a}"
TIMEOUT="${2:-420}"
docker exec docker-agents-mailbus-1 python3 /mailbus/tools/smoke-agent-disk-write.py \
  --agent "$AGENT" --data-dir /mailbus/store --timeout "$TIMEOUT"
