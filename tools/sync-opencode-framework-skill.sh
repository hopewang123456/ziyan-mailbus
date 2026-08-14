#!/usr/bin/env bash
# OpenCode（编码 agent）framework + role skills → opencode/skills/
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AI_TOOLS="$(cd "$ROOT/.." && pwd)"
AGENT="${OPENCODE_AGENT:-agent-i}"
TARGET="${OPENCODE_SKILLS_DIR:-$AI_TOOLS/opencode/skills}"
DATA_DIR="${DATA_DIR:-$ROOT/store}"

mkdir -p "$TARGET"
if [ -f "$ROOT/tools/sync_framework_workspace_skills.py" ]; then
  python3 "$ROOT/tools/sync_framework_workspace_skills.py" "$AGENT" "$TARGET" --data-dir "$DATA_DIR" --symlink
else
  echo "[sync-opencode-framework-skill] skip (workspace skills = runtime junction, Vault SoT)"
fi
echo "[sync-opencode-framework-skill] agent=$AGENT target=$TARGET"
