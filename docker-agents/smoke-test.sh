#!/bin/bash
# 启动后自检：mailbus / Hermes / OpenClaw / DeepSeek API
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

pass=0
fail=0
WAIT_SEC="${SMOKE_WAIT_SEC:-20}"

check_http() {
  local name="$1" url="$2"
  local code i
  for i in $(seq 1 6); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 "$url" 2>/dev/null || echo "000")
    if [[ "$code" =~ ^(200|301|302|401|404)$ ]]; then
      echo "OK  $name  $url  ($code)"
      pass=$((pass + 1))
      return 0
    fi
    sleep 5
  done
  echo "FAIL $name  $url  ($code)"
  fail=$((fail + 1))
  return 1
}

echo "=== smoke test $(date '+%Y-%m-%d %H:%M:%S') ==="
echo "waiting ${WAIT_SEC}s for services..."
sleep "$WAIT_SEC"

check_http "mailbus"           "http://127.0.0.1:9812/"
check_http "lingzhao-9120"     "http://127.0.0.1:9120/"
check_http "lingjin-9121"      "http://127.0.0.1:9121/"
check_http "lingxi-9122"       "http://127.0.0.1:9122/"
check_http "lingtuo-9126"      "http://127.0.0.1:9126/"
check_http "lingxun-9125"      "http://127.0.0.1:9125/"
check_http "lingzhang-9127"    "http://127.0.0.1:9127/"
check_http "openclaw-xiaoqi"   "http://127.0.0.1:18789/"
check_http "openclaw-yige"     "http://127.0.0.1:18790/"
check_http "iii-engine"        "http://127.0.0.1:3111/"
check_http "agentmemory"       "http://127.0.0.1:3111/agentmemory/health"
check_http "codex-lingxiao"    "http://127.0.0.1:9240/"
check_http "codex-lingjian"    "http://127.0.0.1:9241/"
check_http "codex-lingxiao-ttyd" "http://127.0.0.1:9250/"
check_http "codex-lingjian-ttyd" "http://127.0.0.1:9251/"
check_http "claude-lingyun"    "http://127.0.0.1:9260/"
check_http "claude-lingyan"    "http://127.0.0.1:9261/"

if [ -x /mnt/c/Windows/System32/curl.exe ]; then
  win_code=$(/mnt/c/Windows/System32/curl.exe -s -o /mnt/c/Windows/NUL -w '%{http_code}' --connect-timeout 8 http://localhost:9812/ 2>/dev/null | tr -d '\r\n')
  if [ "$win_code" = "200" ]; then
    echo "OK  windows-localhost-9812  http://localhost:9812/  ($win_code)"
    pass=$((pass + 1))
  else
    echo "FAIL windows-localhost-9812  http://localhost:9812/  ($win_code)"
    fail=$((fail + 1))
  fi
fi

echo "--- Hermes API ---"
proxy=$(docker exec docker-agents-hermes-1 printenv HTTP_PROXY 2>/dev/null || echo "")
echo "HTTP_PROXY=${proxy:-<empty>}"
ds=$(docker exec docker-agents-hermes-1 curl -s -o /dev/null -w '%{http_code}' --connect-timeout 15 https://api.deepseek.com/v1/models 2>/dev/null || echo "000")
if [ "$ds" = "401" ] || [ "$ds" = "200" ]; then
  echo "OK  deepseek-api ($ds)"
  pass=$((pass + 1))
else
  echo "FAIL deepseek-api ($ds)"
  fail=$((fail + 1))
fi

echo "--- Hermes chat (lingzhao) ---"
chat_out=$(docker exec docker-agents-hermes-1 hermes chat -Q -q "回复一个字：好" --profile lingzhao 2>&1 || true)
if echo "$chat_out" | grep -q "session_id:"; then
  echo "OK  hermes-chat lingzhao"
  pass=$((pass + 1))
else
  echo "FAIL hermes-chat lingzhao"
  echo "$chat_out" | tail -5
  fail=$((fail + 1))
fi

echo "--- Internal LLM health ---"
llm_out=$(docker exec docker-agents-mailbus-1 python3 /mailbus/tools/setup-internal-llm.py --data-dir /mailbus/store --json 2>/dev/null || echo "{}")
if echo "$llm_out" | grep -q '"ready": true'; then
  echo "OK  internal-llm ready"
  pass=$((pass + 1))
elif echo "$llm_out" | grep -q '"active_provider": "local"'; then
  echo "OK  internal-llm local active"
  pass=$((pass + 1))
else
  echo "WARN internal-llm not ready (remote fallback may be needed)"
  echo "$llm_out" | head -5
fi

if [ "${SMOKE_AM_PERSIST:-0}" = "1" ]; then
  echo "--- AgentMemory persistence probe ---"
  if python3 "$SCRIPT_DIR/../tools/check-agentmemory-persistence.py" --url http://127.0.0.1:3111; then
    echo "OK  agentmemory-persistence"
    pass=$((pass + 1))
  else
    echo "FAIL agentmemory-persistence"
    fail=$((fail + 1))
  fi
fi

echo "=== result: $pass passed, $fail failed ==="
exit $fail
