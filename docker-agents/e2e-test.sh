#!/bin/bash
# 端到端测试：服务 + Clash 代理开/关
set -uo pipefail

COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${COMPOSE_DIR}/lib/api-url.sh"

PS="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
PASS=0
FAIL=0
ORIG_PROXY_ENABLE=""

log() { echo "$*"; }

ok()  { log "OK   $*"; PASS=$((PASS + 1)); }
bad() { log "FAIL $*"; FAIL=$((FAIL + 1)); }

get_proxy_enable() {
  "$PS" -NoProfile -Command \
    "(Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings').ProxyEnable" \
    2>/dev/null | tr -d '\r\n' || echo "0"
}

set_proxy_enable() {
  local v="$1"
  "$PS" -NoProfile -Command \
    "Set-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -Name ProxyEnable -Value $v" \
    >/dev/null 2>&1 || return 1
}

apply_proxy_config() {
  bash "$COMPOSE_DIR/setup-container-proxy.sh"
  cd "$COMPOSE_DIR"
  docker compose up -d --force-recreate hermes openclaw dali lingxiao 2>/dev/null
  sleep 25
  # 等待 Hermes dashboard 就绪
  for i in $(seq 1 12); do
    c=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 3 http://127.0.0.1:9120/ 2>/dev/null || echo "000")
    [ "$c" = "200" ] && break
    sleep 5
  done
}

test_deepseek_from_hermes() {
  local label="$1"
  local expect_proxy="$2"  # empty or non-empty
  local actual
  actual=$(docker exec docker-agents-hermes-1 printenv HTTP_PROXY 2>/dev/null || true)
  local code
  code=$(docker exec docker-agents-hermes-1 curl -s -o /dev/null -w '%{http_code}' \
    --connect-timeout 15 https://api.deepseek.com/v1/models 2>/dev/null || echo "000")
  local chat_ok=0
  if docker exec docker-agents-hermes-1 hermes chat -Q -q "回复一个字：好" --profile lingzhao 2>&1 | grep -q "session_id:"; then
    chat_ok=1
  fi
  log "  [$label] HTTP_PROXY=[${actual:-<empty>}] deepseek=$code chat=$chat_ok"
  if [ "$expect_proxy" = "empty" ] && [ -n "$actual" ]; then
    bad "$label: expected no proxy but got $actual"
    return
  fi
  if [ "$expect_proxy" = "set" ] && [ -z "$actual" ]; then
    bad "$label: expected proxy but HTTP_PROXY empty"
    return
  fi
  if [ "$code" != "401" ] && [ "$code" != "200" ]; then
    bad "$label: deepseek API unreachable ($code)"
    return
  fi
  if [ "$chat_ok" -ne 1 ]; then
    bad "$label: hermes chat failed"
    return
  fi
  ok "$label: proxy=${actual:-direct} deepseek=$code chat=ok"
}

test_endpoints() {
  local label="$1"
  local code_api code9120 code9121 win_api
  code_api=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 http://127.0.0.1:${MAILBUS_API_PORT}/ 2>/dev/null || echo "000")
  code9120=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 http://127.0.0.1:9120/ 2>/dev/null || echo "000")
  code9121=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 http://127.0.0.1:9121/ 2>/dev/null || echo "000")
  if [ -x /mnt/c/Windows/System32/curl.exe ]; then
    win_api=$(/mnt/c/Windows/System32/curl.exe -s -o /mnt/c/Windows/NUL -w '%{http_code}' \
      --connect-timeout 8 http://localhost:${MAILBUS_API_PORT}/ 2>/dev/null | tr -d '\r\n')
  else
    win_api="skip"
  fi
  log "  [$label] wsl_api=$code_api wsl9120=$code9120 wsl9121=$code9121 win_api=$win_api"
  if [ "$code_api" = "200" ] && [ "$code9120" = "200" ] && [ "$code9121" = "200" ]; then
    if [ "$win_api" = "200" ] || [ "$win_api" = "skip" ]; then
      ok "$label: all web endpoints up"
      return
    fi
  fi
  bad "$label: endpoint check failed"
  /mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -ExecutionPolicy Bypass \
    -File "E:\\ai_tools\\scripts\\fix-wsl-localhost.ps1" >/dev/null 2>&1 || true
  sleep 2
  win_api=$(/mnt/c/Windows/System32/curl.exe -s -o /mnt/c/Windows/NUL -w '%{http_code}' \
    --connect-timeout 8 http://localhost:${MAILBUS_API_PORT}/ 2>/dev/null | tr -d '\r\n')
  if [ "$code_api" = "200" ] && [ "$win_api" = "200" ]; then
    ok "$label: endpoints recovered after port fix"
  fi
}

test_agentmemory() {
  local code
  code=$(docker exec docker-agents-mailbus-1 python3 -c "
import urllib.request
try:
  r=urllib.request.urlopen('http://iii-engine:3111/', timeout=5)
  print(r.status)
except Exception as e:
  print(getattr(e,'code',0) or '000')
" 2>/dev/null | tr -d '\r\n')
  if [[ "$code" =~ ^(200|401|404)$ ]]; then
    ok "agentmemory iii-engine:3111 reachable ($code)"
  else
    bad "agentmemory unreachable ($code)"
  fi
}

cleanup() {
  if [ -n "$ORIG_PROXY_ENABLE" ]; then
    log "[cleanup] restoring ProxyEnable=$ORIG_PROXY_ENABLE"
    set_proxy_enable "$ORIG_PROXY_ENABLE"
    apply_proxy_config
  fi
}
trap cleanup EXIT

log "=== E2E test $(date '+%Y-%m-%d %H:%M:%S') ==="

ORIG_PROXY_ENABLE=$(get_proxy_enable)
log "Current Windows ProxyEnable=$ORIG_PROXY_ENABLE"

log "--- Phase 1: full start-team ---"
rm -f /tmp/start-team.lock
bash "$COMPOSE_DIR/start-team.sh" || bad "start-team failed"

log "--- Phase 2: endpoints + agentmemory ---"
test_endpoints "after-start"
test_agentmemory

log "--- Phase 3: proxy OFF (direct) ---"
set_proxy_enable 0
apply_proxy_config
grep CONTAINER "$COMPOSE_DIR/.env" || true
test_deepseek_from_hermes "proxy-OFF" "empty"

log "--- Phase 4: proxy ON (Clash) ---"
WIN_HOST=$(ip route show default 2>/dev/null | awk '{print $3}' | head -1)
CLASH_OK=0
if curl -s -o /dev/null --connect-timeout 3 -x "http://${WIN_HOST}:7897" \
  "https://api.deepseek.com/v1/models" >/dev/null 2>&1; then
  CLASH_OK=1
fi
if [ "$CLASH_OK" -eq 1 ]; then
  set_proxy_enable 1
  apply_proxy_config
  grep CONTAINER "$COMPOSE_DIR/.env" || true
  test_deepseek_from_hermes "proxy-ON" "set"
else
  bad "proxy-ON: Clash :7897 not reachable on $WIN_HOST — skip (is Clash running?)"
fi

log "--- Phase 5: restore original proxy state ---"
set_proxy_enable "$ORIG_PROXY_ENABLE"
apply_proxy_config

log "--- Phase 6: stability 60s ---"
if bash "$COMPOSE_DIR/stability-test.sh"; then
  ok "stability 60s"
else
  bad "stability 60s"
fi

log "=== E2E result: $PASS passed, $FAIL failed ==="
exit $FAIL
