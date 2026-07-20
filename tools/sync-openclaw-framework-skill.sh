#!/usr/bin/env bash
# OpenClaw（小七/一哥）framework skills → openclaw_space/skills/
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AI_TOOLS="$(cd "$ROOT/.." && pwd)"
AGENT="${OPENCLAW_AGENT:-xiaoqi}"
TARGET="${OPENCLAW_SKILLS_DIR:-$AI_TOOLS/openclaw_space/skills}"
DATA_DIR="${DATA_DIR:-$ROOT/store}"

mkdir -p "$TARGET"
python3 "$ROOT/tools/sync_framework_workspace_skills.py" "$AGENT" "$TARGET" --data-dir "$DATA_DIR" --symlink
echo "[sync-openclaw-framework-skill] agent=$AGENT target=$TARGET"
