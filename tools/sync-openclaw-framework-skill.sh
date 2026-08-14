#!/usr/bin/env bash
# OpenClaw（调度/内容 agent）framework skills → openclaw_space/skills/
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AI_TOOLS="$(cd "$ROOT/.." && pwd)"
AGENT="${OPENCLAW_AGENT:-agent-m}"
TARGET="${OPENCLAW_SKILLS_DIR:-$AI_TOOLS/openclaw_space/skills}"
DATA_DIR="${DATA_DIR:-$ROOT/store}"

mkdir -p "$TARGET"
if [ -f "$ROOT/tools/sync_framework_workspace_skills.py" ]; then
  python3 "$ROOT/tools/sync_framework_workspace_skills.py" "$AGENT" "$TARGET" --data-dir "$DATA_DIR" --symlink
else
  echo "[sync-openclaw-framework-skill] skip (workspace skills = runtime junction, Vault SoT)"
fi
echo "[sync-openclaw-framework-skill] agent=$AGENT target=$TARGET"
