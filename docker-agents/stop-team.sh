#!/bin/bash
# 子言 AI 团队 Docker 停止脚本（由桌面 .bat 调用）

kill_if_running() {
  local pattern="$1"
  pgrep -f "$pattern" 2>/dev/null | while read -r pid; do
    [ -n "$pid" ] || continue
    local cmd
    cmd=$(tr '\0' ' ' < "/proc/${pid}/cmdline" 2>/dev/null || true)
    case "$cmd" in
      *"$pattern"*) kill "$pid" 2>/dev/null || true ;;
    esac
  done
}

if systemctl is-enabled mailbus-watchdog >/dev/null 2>&1; then
  sudo systemctl stop mailbus-watchdog 2>/dev/null || true
else
  kill_if_running "/mnt/e/ai_tools/mail/mailbus-launch-watchdog.sh"
fi
sleep 1

COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$COMPOSE_DIR"
docker compose down

echo "All containers stopped"
