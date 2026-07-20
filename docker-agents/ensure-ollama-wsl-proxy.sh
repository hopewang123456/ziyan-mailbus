#!/bin/bash
# Start/stop WSL proxy so Docker mailbus can reach Windows Ollama.
set -uo pipefail

COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIL_DIR="$(cd "$COMPOSE_DIR/.." && pwd)"
PID_FILE="/tmp/ollama-wsl-proxy.pid"
LOG="/tmp/ollama-wsl-proxy.log"
PROXY="$MAIL_DIR/tools/ollama-wsl-proxy.py"
WAIT_SECONDS="${OLLAMA_WSL_PROXY_WAIT_SECONDS:-90}"

stop_proxy() {
  if [ -f "$PID_FILE" ]; then
    old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
      kill "$old_pid" 2>/dev/null || true
      sleep 1
    fi
    rm -f "$PID_FILE"
  fi
}

wait_for_windows_ollama() {
  local i
  for i in $(seq 1 "$WAIT_SECONDS"); do
    if /mnt/c/Windows/System32/curl.exe -sf --max-time 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

start_proxy() {
  if [ ! -f "$PROXY" ]; then
    echo "[ollama-wsl-proxy] missing $PROXY" >&2
    return 1
  fi
  if ! wait_for_windows_ollama; then
    echo "[ollama-wsl-proxy] Windows Ollama not ready after ${WAIT_SECONDS}s — skip" >&2
    return 1
  fi
  stop_proxy
  nohup python3 "$PROXY" --host 0.0.0.0 --port 11434 >>"$LOG" 2>&1 &
  echo $! >"$PID_FILE"
  sleep 1
  if curl -sf --max-time 5 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "[ollama-wsl-proxy] OK pid=$(cat "$PID_FILE")"
    return 0
  fi
  echo "[ollama-wsl-proxy] failed to bind/listen — see $LOG" >&2
  stop_proxy
  return 1
}

case "${1:-start}" in
  start) start_proxy ;;
  stop) stop_proxy ;;
  restart) stop_proxy; start_proxy ;;
  status)
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "running pid=$(cat "$PID_FILE")"
    else
      echo "stopped"
    fi
    ;;
  *) echo "usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
