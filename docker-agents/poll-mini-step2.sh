#!/bin/bash
# 轮询 mini pipeline Step2 完成（容器内读 store，避免 WSL 权限问题）
set -euo pipefail
TASK="${1:-}"
TIMEOUT="${2:-720}"
POLL="${3:-30}"

docker exec docker-agents-mailbus-1 env \
  TASK_ID="${TASK}" TIMEOUT="${TIMEOUT}" POLL="${POLL}" \
  python3 /mailbus/tools/_archive/poll-mini-step2.py
