#!/usr/bin/env bash
# Hermes profile agents：验证 adapters 挂载；可选同步到 HERMES_FRAMEWORK_SKILLS_DIR
# 注意：.sync 仅为镜像缓存。运行时 SoT = Vault（profiles/*/skills junction）。
# 默认 --symlink；设 HERMES_SKILL_COPY=1 才写实体副本。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AI_TOOLS="$(cd "$ROOT/.." && pwd)"
AGENT="${HERMES_AGENT:-lingzhao}"
ADAPTERS_MOUNT="${HERMES_ADAPTERS_DIR:-/mailbus/access}"
DATA_DIR="${DATA_DIR:-$ROOT/store}"
TARGET="${HERMES_FRAMEWORK_SKILLS_DIR:-$AI_TOOLS/mail/access/hermes/.sync/$AGENT/skills}"
COPY_FLAG=""
if [ "${HERMES_SKILL_COPY:-}" = "1" ]; then
  COPY_FLAG="--copy"
fi

if [ -d "$ADAPTERS_MOUNT" ]; then
  echo "[sync-hermes-framework-skill] adapters mount ok: $ADAPTERS_MOUNT"
else
  echo "[sync-hermes-framework-skill] warn: $ADAPTERS_MOUNT not found (mount mail/access in compose)"
fi

mkdir -p "$TARGET"
SYNC_PY=""
if [ -f "$ROOT/tools/sync_framework_workspace_skills.py" ]; then
  SYNC_PY="$ROOT/tools/sync_framework_workspace_skills.py"
elif [ -f "$ROOT/tools/_archive/sync_framework_workspace_skills.py" ]; then
  SYNC_PY="$ROOT/tools/_archive/sync_framework_workspace_skills.py"
fi
if [ -n "$SYNC_PY" ]; then
  # shellcheck disable=SC2086
  python3 "$SYNC_PY" "$AGENT" "$TARGET" --data-dir "$DATA_DIR" --symlink $COPY_FLAG
else
  echo "[sync-hermes-framework-skill] warn: sync_framework_workspace_skills.py missing; skip"
fi
echo "[sync-hermes-framework-skill] agent=$AGENT target=$TARGET (SoT=Vault; .sync=mirror)"
