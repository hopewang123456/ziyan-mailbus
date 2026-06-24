#!/bin/bash
set -euo pipefail
c="${1:-docker-agents-lingxiao-1}"
docker exec "$c" bash -lc '
run() {
  local label="$1"; shift
  echo "=== $label ==="
  timeout 90 "$@" 2>&1 | tail -8 || echo "[timeout/fail] $label"
  echo
}

run "never-en" codex exec --json --ephemeral --skip-git-repo-check --cd /mailbus/store \
  -s workspace-write -c '"'"'approval_policy="never"'"'"' \
  -m deepseek-v4-flash "Reply exactly OK"

run "never-zh" codex exec --json --ephemeral --skip-git-repo-check --cd /mailbus/store \
  -s workspace-write -c '"'"'approval_policy="never"'"'"' \
  -m deepseek-v4-flash "你好，只回复OK"

run "on-request-en" codex exec --json --ephemeral --skip-git-repo-check --cd /mailbus/store \
  -s workspace-write -c '"'"'approval_policy="on-request"'"'"' \
  -m deepseek-v4-flash "Reply exactly OK"

run "gateway-direct" curl -sf -m 30 http://127.0.0.1:3000/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${DEEPSEEK_API_KEY}" \
  -d '"'"'{"model":"deepseek-chat","input":"Say OK"}'"'"' | head -c 400; echo
'
