#!/usr/bin/env bash
# Hermes profile agents：验证 adapters 挂载；可选按 agent 同步到 HERMES_FRAMEWORK_SKILLS_DIR
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AI_TOOLS="$(cd "$ROOT/.." && pwd)"
AGENT="${HERMES_AGENT:-lingzhao}"
ADAPTERS_MOUNT="${HERMES_ADAPTERS_DIR:-/mailbus/adapters}"
DATA_DIR="${DATA_DIR:-$ROOT/store}"
TARGET="${HERMES_FRAMEWORK_SKILLS_DIR:-$AI_TOOLS/mail/adapters/.sync/$AGENT/skills}"
COPY_FLAG=""
if [ "${HERMES_SKILL_COPY:-}" = "1" ]; then
  COPY_FLAG="--copy"
fi

# 容器内：/mailbus/adapters 只读挂载即可被 agent Read；宿主机同步副本便于本地 Hermes
if [ -d "$ADAPTERS_MOUNT" ]; then
  echo "[sync-hermes-framework-skill] adapters mount ok: $ADAPTERS_MOUNT"
else
  echo "[sync-hermes-framework-skill] warn: $ADAPTERS_MOUNT not found (mount mail/adapters in compose)"
fi

mkdir -p "$TARGET"
python3 "$ROOT/tools/sync_framework_workspace_skills.py" "$AGENT" "$TARGET" --data-dir "$DATA_DIR" --symlink $COPY_FLAG
echo "[sync-hermes-framework-skill] agent=$AGENT target=$TARGET"
