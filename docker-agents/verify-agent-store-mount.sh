#!/bin/bash
# 验证各 agent 容器能否读写 mailbus 共享 store（不改 agent 源码）
set -euo pipefail

MAIL="/mnt/e/ai_tools/mail"
PROBE="mailbus-mount-probe-$$.txt"
STORE="/mailbus/store"
PASS=0
FAIL=0

check() {
  local name="$1"
  local cmd="$2"
  echo -n "  $name ... "
  if eval "$cmd" >/dev/null 2>&1; then
    echo "OK"
    PASS=$((PASS + 1))
  else
    echo "FAIL"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== verify-agent-store-mount ==="

check "mailbus 写 store" \
  "docker exec docker-agents-mailbus-1 sh -c 'echo ok > ${STORE}/.${PROBE} && rm -f ${STORE}/.${PROBE}'"

check "hermes 写 store" \
  "docker exec docker-agents-hermes-1 sh -c 'echo ok > ${STORE}/.${PROBE} && rm -f ${STORE}/.${PROBE}'"

check "hermes 读 rules" \
  "docker exec docker-agents-hermes-1 test -f /mailbus/rules/pipeline-agent-paths.md"

check "openclaw 写 store" \
  "docker exec docker-agents-openclaw-1 sh -c 'echo ok > ${STORE}/.${PROBE} && rm -f ${STORE}/.${PROBE}'"

check "dali 写 store" \
  "docker exec docker-agents-dali-1 sh -c 'echo ok > ${STORE}/.${PROBE} && rm -f ${STORE}/.${PROBE}'"

check "lingxiao 写 store" \
  "docker exec docker-agents-lingxiao-1 sh -c 'echo ok > ${STORE}/.${PROBE} && rm -f ${STORE}/.${PROBE}'"

check "lingjian 写 store" \
  "docker exec docker-agents-lingjian-1 sh -c 'echo ok > ${STORE}/.${PROBE} && rm -f ${STORE}/.${PROBE}'"

echo "---"
echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
