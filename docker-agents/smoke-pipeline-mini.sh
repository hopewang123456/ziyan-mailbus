#!/bin/bash
# Mini pipeline 2 步自动化 gate（v3 前）
set -euo pipefail
STEP_TIMEOUT="${1:-600}"
docker exec docker-agents-mailbus-1 python3 /mailbus/tools/smoke-pipeline-mini.py \
  --data-dir /mailbus/store --step-timeout "$STEP_TIMEOUT"
