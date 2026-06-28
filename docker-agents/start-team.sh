#!/bin/bash
# 子言 AI 团队 Docker 启动脚本（由桌面 .bat 调用）
set -uo pipefail

COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${COMPOSE_DIR}/lib/mailbus-env.sh"
. "${COMPOSE_DIR}/lib/api-url.sh"

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
  echo "[start-team] 已有启动任务在跑，跳过（若卡住请删 /tmp/start-team.lock 后重试）"
  exit 0
fi

log "=== start-team $(date '+%Y-%m-%d %H:%M:%S') ==="

log "Waiting for Docker daemon..."
docker_ok=0
for i in $(seq 1 45); do
  if docker info >/dev/null 2>&1; then
    docker_ok=1
    break
  fi
  sleep 2
done
if [ "$docker_ok" -ne 1 ]; then
  log "ERROR: Docker not running after 90s. Try: sudo service docker start"
  echo "[ERROR] Docker 未就绪。请在 WSL 执行: sudo service docker start"
  exit 1
fi

log "Syncing team rules to bulletin + AgentMemory..."
docker exec docker-agents-mailbus-1 python3 /mailbus/tools/ops/tools/ops/sync-team-rules.py --data-dir /mailbus/store 2>&1 >> "$LOG" || true

log "Cleaning legacy host mailbus cron (Docker built-in scheduler owns scan/jobs)..."
bash "$COMPOSE_DIR/uninstall-mailbus-cron.sh" 2>&1 >> "$LOG"

log "Stopping legacy host services that conflict with Docker..."
if pgrep -f "/mnt/e/ai_tools/openclaw-watchdog.py" >/dev/null 2>&1; then
  pkill -f "/mnt/e/ai_tools/openclaw-watchdog.py" 2>/dev/null || true
fi
# 杀掉宿主机上占用 MAILBUS_API_PORT 的非 Docker 进程
ss -tlnp 2>/dev/null | grep ':${MAILBUS_API_PORT} ' | grep -oP 'pid=\K[0-9]+' | sort -u | while read -r pid; do
  [ -n "$pid" ] || continue
  if [ -f "/proc/${pid}/cgroup" ] && grep -q "docker" "/proc/${pid}/cgroup" 2>/dev/null; then
    continue
  fi
  log "Killing host process on :${MAILBUS_API_PORT} pid=$pid"
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

log "Syncing L0-L2 agent layer skills + Claude context (host)..."
python3 /mnt/e/ai_tools/mail/tools/patch-skills-index-framework.py \
  --data-dir /mnt/e/ai_tools/mail/store 2>&1 >> "$LOG" || true
python3 /mnt/e/ai_tools/mail/tools/sync-all-agent-layers.py \
  --data-dir /mnt/e/ai_tools/mail/store 2>&1 >> "$LOG" || true

log "Ensuring Windows host Ollama (internal LLM)..."
/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -ExecutionPolicy Bypass \
  -File "E:\\ai_tools\\mail\\docker-agents\\ensure-ollama.ps1" 2>&1 >> "$LOG" || \
  log "WARNING: ensure-ollama failed — internal LLM may fall back to remote"

log "Configuring container proxy (Clash on/off)..."
bash "$COMPOSE_DIR/setup-container-proxy.sh" 2>&1 >> "$LOG"

NEW_PROXY="$(grep '^CONTAINER_HTTP_PROXY=' "$COMPOSE_DIR/.env" 2>/dev/null | cut -d= -f2- || true)"

log "Ensuring Docker containers are up (no compose down)..."
cd "$COMPOSE_DIR"
if ! docker compose up -d --remove-orphans 2>&1 >> "$LOG"; then
  log "First start failed, trying rebuild..."
  docker compose up -d --build --remove-orphans 2>&1 >> "$LOG"
fi

# Hermes entrypoint 曾缺 lingtuo/lingzhang；若 9126 未监听则强制重建 hermes 镜像
hermes_tuo_code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 http://127.0.0.1:9126/ 2>/dev/null || echo "000")
if [ "$hermes_tuo_code" = "000" ]; then
  log "Hermes :9126 not responding — rebuild/recreate hermes (6-profile entrypoint)..."
  docker compose build hermes 2>&1 >> "$LOG" || true
  docker compose up -d --force-recreate hermes 2>&1 >> "$LOG" || true
  sleep 8
fi
# 仅代理 env 变更时重建相关容器，避免 e2e/重复启动时无谓 bounce
if [ "$NEW_PROXY" != "$OLD_PROXY" ]; then
  log "Proxy changed [$OLD_PROXY] -> [$NEW_PROXY], recreating proxy-sensitive containers..."
  docker compose up -d --force-recreate hermes openclaw dali lingxiao lingjian 2>&1 >> "$LOG" || true
else
  log "Proxy unchanged, skip force-recreate"
fi

log "Waiting for mailbus/Hermes to become ready..."
ready=0
for i in $(seq 1 24); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 http://127.0.0.1:${MAILBUS_API_PORT}/ 2>/dev/null || echo "000")
  if [ "$code" = "200" ]; then
    ready=1
    break
  fi
  sleep 5
done
if [ "$ready" -eq 0 ]; then
  log "WARNING: mailbus :${MAILBUS_API_PORT} not ready after 120s"
else
  log "mailbus :${MAILBUS_API_PORT} ready"
  log "Probing internal LLM + RAG bootstrap..."
  docker exec docker-agents-mailbus-1 python3 /mailbus/tools/ops/tools/ops/setup-internal-llm.py \
    --data-dir /mailbus/store --rebuild-rag-if-empty --json 2>&1 >> "$LOG" || \
    log "WARNING: internal LLM probe/RAG bootstrap failed"
fi

log "Waiting for AgentMemory HTTP (iii-engine:3111)..."
am_ready=0
for i in $(seq 1 45); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 http://127.0.0.1:3111/agentmemory/health 2>/dev/null || echo "000")
  if [ "$code" = "200" ]; then
    am_ready=1
    break
  fi
  sleep 1
done
if [ "$am_ready" -eq 1 ]; then
  log "AgentMemory ready"
else
  log "WARNING: AgentMemory not ready after 45s"
fi

log "Bootstrapping Codex Web UI (lingxiao + lingjian)..."
if [ -x "$COMPOSE_DIR/apply-codex-ui.sh" ]; then
  bash "$COMPOSE_DIR/apply-codex-ui.sh" 2>&1 >> "$LOG" || log "WARNING: apply-codex-ui failed"
fi

log "Starting Claude Code agents (lingyun/lingyan ttyd)..."
if [ -x "$COMPOSE_DIR/ensure-claude-agents.sh" ]; then
  bash "$COMPOSE_DIR/ensure-claude-agents.sh" /mnt/e/ai_tools/mail/store "$LOG" 2>&1 >> "$LOG" || \
    log "WARNING: Claude Code ttyd start failed (need tmux + ttyd in WSL)"
fi

log "Starting mailbus CLI watchdog..."
bash /mnt/e/ai_tools/mail/docker-agents/restart-watchdog.sh 2>&1 >> "$LOG"

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
