#!/bin/bash
# Inspect Hermes volume mounts — relative to this repo (no hard-coded ai_tools).
set -eux
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MAILBUS_ROOT="$(cd "$COMPOSE_DIR/.." && pwd)"
C="${HERMES_CONTAINER:-docker-agents-hermes-1}"

docker inspect "$C" --format '{{range .Mounts}}{{.Type}} {{.Source}} -> {{.Destination}}{{"\n"}}{{end}}' || true
echo ---
grep -n HERMES "$COMPOSE_DIR/.env" 2>/dev/null || true
grep -n HERMES "$COMPOSE_DIR/docker-compose.yml" | head -20 || true
echo ---
for p in \
  "${HERMES_DATA:-$COMPOSE_DIR/workspaces/hermes-data}" \
  "$MAILBUS_ROOT/.local/hermes" \
  /var/lib/docker/volumes
do
  ls -ld "$p" 2>/dev/null || true
done
docker volume ls | grep -i hermes || true
