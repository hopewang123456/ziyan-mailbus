#!/usr/bin/env bash
# Restart mailbus (Docker compose mailbus service or native bus.py serve)
# Usage: bash tools/restart-mailbus.sh [port]
set -euo pipefail
PORT="${1:-9814}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

health() {
  curl -sf --connect-timeout 5 "http://127.0.0.1:${PORT}/" >/dev/null 2>&1
}

if command -v docker >/dev/null 2>&1; then
  COMPOSE_DIR="$ROOT/docker-agents"
  if [ -f "$COMPOSE_DIR/docker-compose.yml" ]; then
    if (cd "$COMPOSE_DIR" && docker compose ps --status running --services 2>/dev/null | grep -qx mailbus); then
      echo "[restart] Docker mailbus ..."
      (cd "$COMPOSE_DIR" && docker compose restart mailbus)
      sleep 8
      if health; then
        echo "[restart] OK http://127.0.0.1:${PORT}/"
        exit 0
      fi
      echo "[restart] Docker mailbus not responding yet" >&2
      exit 1
    fi
  fi
fi

echo "[restart] stopping native bus.py serve ..."
pkill -f "bus.py serve" 2>/dev/null || true
sleep 2

LOG_DIR="$ROOT/store/logs"
mkdir -p "$LOG_DIR"
LOG_OUT="$LOG_DIR/mailbus-serve.out.log"
LOG_ERR="$LOG_DIR/mailbus-serve.err.log"
echo "[restart] starting native mailbus serve ..."
nohup python3 bus.py serve --host 127.0.0.1 --port "$PORT" --data-dir store \
  >>"$LOG_OUT" 2>>"$LOG_ERR" &
for _ in $(seq 1 15); do
  sleep 2
  if health; then
    echo "[restart] OK http://127.0.0.1:${PORT}/ (logs: $LOG_OUT)"
    exit 0
  fi
done
echo "[restart] mailbus not ready; see $LOG_OUT and $LOG_ERR" >&2
exit 1
