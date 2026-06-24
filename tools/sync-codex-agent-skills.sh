#!/bin/bash
# 从 skills-index 同步 Codex agent skills + memory 快照到 CODEX_HOME/skills
set -euo pipefail

AGENT="${1:-}"
CODEX_HOME="${2:-${CODEX_HOME:-/home/node/.codex}}"
DATA_DIR="${3:-/mailbus/store}"

if [ -z "$AGENT" ]; then
  echo "Usage: sync-codex-agent-skills.sh <agent> [codex_home] [data_dir]" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export MAILBUS_ROOT="$ROOT"
export CODEX_AGENT="$AGENT"
export CODEX_HOME DATA_DIR

python3 "$ROOT/tools/sync_codex_agent_skills.py"
