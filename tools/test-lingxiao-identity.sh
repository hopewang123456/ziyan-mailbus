#!/bin/bash
set -euo pipefail
docker exec docker-agents-lingxiao-1 bash -lc '
export CODEX_HOME=/home/node/.codex
codex exec --json --ephemeral --skip-git-repo-check --cd /mailbus/store \
  -s workspace-write -c "approval_policy=\"never\"" \
  -m deepseek-v4-flash "你是谁？用一句话回答，必须包含名字灵霄" 2>&1 | tail -8
'
