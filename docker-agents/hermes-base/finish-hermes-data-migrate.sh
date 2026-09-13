#!/bin/bash
# Finish Hermes data migrate — paths from env / script location (no ai_tools hardcode).
set -eux

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MAILBUS_ROOT="$(cd "$COMPOSE_DIR/.." && pwd)"
DST="${HERMES_DATA:-$COMPOSE_DIR/workspaces/hermes-data}"
SRC="${HERMES_SRC:-$MAILBUS_ROOT/.local/hermes}"
ENVF="${COMPOSE_DIR}/.env"

mkdir -p "$DST"
touch "$ENVF"
if grep -q '^HERMES_DATA=' "$ENVF" 2>/dev/null; then
  sed -i "s|^HERMES_DATA=.*|HERMES_DATA=${DST}|" "$ENVF"
else
  echo "HERMES_DATA=${DST}" >> "$ENVF"
fi

cat <<EOF
HERMES_DATA=${DST}
SRC(optional leftover)=${SRC}
EOF

cd "$COMPOSE_DIR"
docker compose up -d hermes || true
grep '^HERMES_DATA=' "$ENVF"
