#!/bin/bash
# 将 mailbus identities 同步到 Hermes profile SOUL.md（CLI/浏览器身份一致）
set -euo pipefail

IDENTITIES="${HERMES_IDENTITIES_DIR:-/home/hermes/identities}"
PROFILES="${HERMES_HOME:-/home/hermes/.hermes}/profiles"

if [ ! -d "$IDENTITIES" ]; then
  echo "[sync-identities] skip: $IDENTITIES not mounted"
  exit 0
fi

for id_file in "$IDENTITIES"/*.md; do
  [ -f "$id_file" ] || continue
  profile=$(basename "$id_file" .md)
  dest="$PROFILES/$profile/SOUL.md"
  [ -d "$PROFILES/$profile" ] || continue
  cp "$id_file" "$dest"
  echo "[sync-identities] $profile <- $(basename "$id_file")"
done
