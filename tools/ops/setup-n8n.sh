#!/usr/bin/env bash
# Deploy/fix n8n mailbus-multi-publish workflow + sync webhook URL
# Usage: bash tools/tools/ops/setup-n8n.sh [--reset]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
RESET=0
if [ "${1:-}" = "--reset" ]; then
  RESET=1
fi

DA="$ROOT/docker-agents"
if [ "$RESET" = "1" ]; then
  bash "$DA/reset-n8n-workflow.sh"
else
  bash "$DA/ensure-n8n-workflow.sh" || bash "$DA/reset-n8n-workflow.sh"
fi
python3 tools/tools/ops/sync-n8n-url.py
