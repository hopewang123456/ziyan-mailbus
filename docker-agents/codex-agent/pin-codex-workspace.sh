#!/bin/bash
# 启动后锁定 codexapp 工作区为 agent 项目目录（避免「New Chat」落到 projectless 路径）
set -euo pipefail

UI_PORT="${CODEX_UI_PORT:-7681}"
PROJECT_DIR="${CODEX_PROJECT_DIR:-}"
AGENT="${CODEX_AGENT:-codex}"

if [ -z "$PROJECT_DIR" ] || ! command -v curl >/dev/null 2>&1; then
  exit 0
fi

case "$AGENT" in
  lingxiao) LABEL="灵霄" ;;
  lingjian) LABEL="灵鉴" ;;
  *) LABEL="$AGENT" ;;
esac

for _ in $(seq 1 30); do
  curl -sf "http://127.0.0.1:${UI_PORT}/" >/dev/null 2>&1 && break
  sleep 1
done

payload_order=$(python3 -c "import json; print(json.dumps({'order':['${PROJECT_DIR}'],'active':['${PROJECT_DIR}'],'labels':{'${PROJECT_DIR}':'${LABEL}'}}))")

curl -sf -X PUT "http://127.0.0.1:${UI_PORT}/codex-api/workspace-roots-state" \
  -H "Content-Type: application/json" \
  -d "$payload_order" >/dev/null 2>&1 || true

curl -sf -X POST "http://127.0.0.1:${UI_PORT}/codex-api/project-root" \
  -H "Content-Type: application/json" \
  -d "{\"path\":\"${PROJECT_DIR}\",\"label\":\"${LABEL}\",\"createIfMissing\":true}" >/dev/null 2>&1 || true

echo "[pin-codex-workspace] agent=${AGENT} project=${PROJECT_DIR} label=${LABEL}" >&2
