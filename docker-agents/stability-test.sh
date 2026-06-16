#!/bin/bash
# 60 秒稳定性探测：mailbus + Windows localhost + 容器未重启
set -uo pipefail

DURATION="${STABILITY_SEC:-60}"
INTERVAL=10
pass=0
fail=0
start_restarts=$(docker inspect docker-agents-mailbus-1 --format '{{.RestartCount}}' 2>/dev/null || echo "?")

echo "=== stability test ${DURATION}s (interval ${INTERVAL}s) ==="
end=$((SECONDS + DURATION))
while [ $SECONDS -lt $end ]; do
  wsl_code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 http://127.0.0.1:9812/ 2>/dev/null || echo "000")
  if [ -x /mnt/c/Windows/System32/curl.exe ]; then
    win_code=$(/mnt/c/Windows/System32/curl.exe -s -o /mnt/c/Windows/NUL -w '%{http_code}' --connect-timeout 8 http://localhost:9812/ 2>/dev/null | tr -d '\r\n')
  else
    win_code="skip"
  fi
  restarts=$(docker inspect docker-agents-mailbus-1 --format '{{.RestartCount}}' 2>/dev/null || echo "?")
  ts=$(date '+%H:%M:%S')
  if [ "$wsl_code" = "200" ] && { [ "$win_code" = "200" ] || [ "$win_code" = "skip" ]; }; then
    echo "OK  $ts  wsl=$wsl_code win=$win_code restarts=$restarts"
    pass=$((pass + 1))
  else
    echo "FAIL $ts  wsl=$wsl_code win=$win_code restarts=$restarts"
    fail=$((fail + 1))
  fi
  sleep "$INTERVAL"
done

end_restarts=$(docker inspect docker-agents-mailbus-1 --format '{{.RestartCount}}' 2>/dev/null || echo "?")
echo "mailbus RestartCount: $start_restarts -> $end_restarts"
echo "=== result: $pass ok, $fail fail ==="
exit $fail
