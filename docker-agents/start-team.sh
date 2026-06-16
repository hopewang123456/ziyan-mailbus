#!/bin/bash
# 子言 AI 团队 Docker 启动脚本（由桌面 .bat 调用）
set -uo pipefail

COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCK_FILE="/tmp/start-team.lock"
LOG="/tmp/start-team.log"

# 清理过期锁（进程已退出但 lock 文件还在）
if [ -f "$LOCK_FILE" ]; then
  old_pid=$(fuser "$LOCK_FILE" 2>/dev/null | awk '{print $1}' | head -1)
  if [ -n "$old_pid" ] && ! kill -0 "$old_pid" 2>/dev/null; then
    rm -f "$LOCK_FILE"
  fi
fi

log() { echo "[start-team] $*"; echo "[start-team] $*" >> "$LOG"; }

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log "Another start-team is running — exit (do not wait)"
  exit 0
fi

log "=== start-team $(date '+%Y-%m-%d %H:%M:%S') ==="

log "Syncing team rules to bulletin + AgentMemory..."
docker exec docker-agents-mailbus-1 python3 /mailbus/tools/sync-team-rules.py --data-dir /mailbus/store 2>&1 >> "$LOG" || true

log "Cleaning legacy host mailbus cron (Docker built-in scheduler owns scan/jobs)..."
bash "$COMPOSE_DIR/uninstall-mailbus-cron.sh" 2>&1 >> "$LOG"

log "Stopping legacy host services that conflict with Docker..."
if pgrep -f "/mnt/e/ai_tools/openclaw-watchdog.py" >/dev/null 2>&1; then
  pkill -f "/mnt/e/ai_tools/openclaw-watchdog.py" 2>/dev/null || true
fi
# 杀掉宿主机上占用 9812 的非 Docker 进程
ss -tlnp 2>/dev/null | grep ':9812 ' | grep -oP 'pid=\K[0-9]+' | sort -u | while read -r pid; do
  [ -n "$pid" ] || continue
  if [ -f "/proc/${pid}/cgroup" ] && grep -q "docker" "/proc/${pid}/cgroup" 2>/dev/null; then
    continue
  fi
  log "Killing host process on :9812 pid=$pid"
  kill "$pid" 2>/dev/null || true
done
sleep 1

kill_host_port() {
  local port="$1"
  ss -tlnp 2>/dev/null | grep ":${port} " | grep -oP 'pid=\K[0-9]+' | sort -u | while read -r pid; do
    [ -n "$pid" ] || continue
    if [ -f "/proc/${pid}/cgroup" ] && grep -q "docker" "/proc/${pid}/cgroup" 2>/dev/null; then
      continue
    fi
    kill "$pid" 2>/dev/null || true
  done
}
kill_host_port 18789
kill_host_port 18790
sleep 1

PROXY_STATE="$COMPOSE_DIR/.proxy-state"
OLD_PROXY=""
[ -f "$PROXY_STATE" ] && OLD_PROXY="$(cat "$PROXY_STATE")"

log "Configuring container proxy (Clash on/off)..."
bash "$COMPOSE_DIR/setup-container-proxy.sh" 2>&1 >> "$LOG"

NEW_PROXY="$(grep '^CONTAINER_HTTP_PROXY=' "$COMPOSE_DIR/.env" 2>/dev/null | cut -d= -f2- || true)"

log "Ensuring Docker containers are up (no compose down)..."
cd "$COMPOSE_DIR"
if ! docker compose up -d --remove-orphans 2>&1 >> "$LOG"; then
  log "First start failed, trying rebuild..."
  docker compose up -d --build --remove-orphans 2>&1 >> "$LOG"
fi
# 仅代理 env 变更时重建相关容器，避免 e2e/重复启动时无谓 bounce
if [ "$NEW_PROXY" != "$OLD_PROXY" ]; then
  log "Proxy changed [$OLD_PROXY] -> [$NEW_PROXY], recreating proxy-sensitive containers..."
  docker compose up -d --force-recreate hermes openclaw dali lingxiao 2>&1 >> "$LOG" || true
else
  log "Proxy unchanged, skip force-recreate"
fi

log "Waiting for mailbus/Hermes to become ready..."
ready=0
for i in $(seq 1 24); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 http://127.0.0.1:9812/ 2>/dev/null || echo "000")
  if [ "$code" = "200" ]; then
    ready=1
    break
  fi
  sleep 5
done
if [ "$ready" -eq 0 ]; then
  log "WARNING: mailbus :9812 not ready after 120s"
else
  log "mailbus :9812 ready"
fi

log "Starting mailbus CLI watchdog..."
bash /mnt/e/ai_tools/mail/restart-watchdog.sh 2>&1 >> "$LOG"

log "Refreshing Windows localhost port forwarding..."
/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -ExecutionPolicy Bypass -File "E:\\ai_tools\\scripts\\fix-wsl-localhost.ps1" 2>&1 >> "$LOG" || true

log "Running smoke test..."
if bash "$COMPOSE_DIR/smoke-test.sh" 2>&1 >> "$LOG"; then
  log "Smoke test passed"
else
  log "WARNING: smoke test failed — see $LOG"
fi

echo ""
docker compose ps --format 'table {{.Name}}\t{{.Status}}'
