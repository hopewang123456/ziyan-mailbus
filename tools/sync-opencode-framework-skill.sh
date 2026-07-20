#!/usr/bin/env bash
# OpenCode（大力）framework + role skills → opencode/skills/
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AI_TOOLS="$(cd "$ROOT/.." && pwd)"
AGENT="${OPENCODE_AGENT:-dali}"
TARGET="${OPENCODE_SKILLS_DIR:-$AI_TOOLS/opencode/skills}"
DATA_DIR="${DATA_DIR:-$ROOT/store}"

mkdir -p "$TARGET"
python3 "$ROOT/tools/sync_framework_workspace_skills.py" "$AGENT" "$TARGET" --data-dir "$DATA_DIR" --symlink
echo "[sync-opencode-framework-skill] agent=$AGENT target=$TARGET"
