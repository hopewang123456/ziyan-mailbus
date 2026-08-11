#!/bin/bash
# 确保 Hermes 容器内 6 个编制 dashboard 全部就绪
# 薄包装 → 实际逻辑在 lib/adapters/frameworks/hermes_dashboard.py
set -euo pipefail

CONTAINER="${HERMES_CONTAINER:-docker-agents-hermes-1}"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "[ensure-hermes] container $CONTAINER not running — skip"
  exit 0
fi

docker exec "$CONTAINER" python3.12 -m lib.adapters.frameworks.hermes_dashboard ensure-all
