#!/bin/bash
# Move Hermes home into HERMES_DATA (no hard-coded ai_tools paths).
# Usage:
#   export HERMES_DATA=/path/to/hermes-data   # optional; default = docker-agents/workspaces/hermes-data
#   ./migrate-hermes-data-dir.sh
set -eux

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MAILBUS_ROOT="$(cd "$COMPOSE_DIR/.." && pwd)"
SRC="${HERMES_SRC:-$MAILBUS_ROOT/.local/hermes}"
DST="${HERMES_DATA:-$COMPOSE_DIR/workspaces/hermes-data}"
ENVF="${COMPOSE_DIR}/.env"

# 1) stop hermes to flush writes
cd "$COMPOSE_DIR"
docker compose stop hermes || docker stop docker-agents-hermes-1 || true
sleep 2

mkdir -p "$DST"

# 2) copy as root via a helper container (src may be root-only)
docker run --rm \
  -v "$SRC:/src:ro" \
  -v "$DST:/dst" \
  alpine:3.20 sh -c '
    set -e
    mkdir -p /dst
    if [ "$(ls -A /dst 2>/dev/null | wc -l)" -gt 0 ] && [ ! -f /dst/.migrated-from-local ]; then
      if [ ! -f /dst/config.yaml ] && [ ! -d /dst/memos-plugin ]; then
        echo "dst not empty and not hermes-looking; abort"
        ls -la /dst
        exit 1
      fi
    fi
    cp -a /src/. /dst/
    date -Iseconds > /dst/.migrated-from-local
    echo "copied"
    ls -la /dst | head -30
    du -sh /dst /dst/memos-plugin 2>/dev/null || true
  '

# 3) set HERMES_DATA in .env
touch "$ENVF"
if grep -q '^HERMES_DATA=' "$ENVF" 2>/dev/null; then
  sed -i "s|^HERMES_DATA=.*|HERMES_DATA=${DST}|" "$ENVF"
else
  printf '\n# Hermes home (profiles / memos-plugin / shared-memory)\nHERMES_DATA=%s\n' "$DST" >> "$ENVF"
fi
grep '^HERMES_DATA=' "$ENVF"

# 4) README
cat > "$DST/README.md" <<EOF
# hermes-data

Hermes runtime data root (\`HERMES_DATA\`).

Set in \`mailbus/docker-agents/.env\`:

\`\`\`
HERMES_DATA=${DST}
\`\`\`
EOF

# 5) restart hermes
cd "$COMPOSE_DIR"
docker compose up -d hermes

echo "done: HERMES_DATA=${DST}"
