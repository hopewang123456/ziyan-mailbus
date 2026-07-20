#!/usr/bin/env bash
# ComfyUI GPU 容器稳定性探测（WSL 内执行）
set -uo pipefail

NAME="${COMFYUI_CONTAINER:-mailbus-comfyui-gpu}"
DURATION="${STABILITY_SEC:-60}"
INTERVAL="${STABILITY_INTERVAL:-10}"
pass=0
fail=0

if ! docker inspect "$NAME" >/dev/null 2>&1; then
  echo "container $NAME not found" >&2
  exit 2
fi

start_restarts=$(docker inspect "$NAME" --format '{{.RestartCount}}')
echo "=== ComfyUI stability ${DURATION}s (interval ${INTERVAL}s) ==="
end=$((SECONDS + DURATION))
while [ $SECONDS -lt $end ]; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 http://127.0.0.1:8188/system_stats 2>/dev/null || echo "000")
  health=$(docker inspect "$NAME" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')
  restarts=$(docker inspect "$NAME" --format '{{.RestartCount}}')
  ts=$(date '+%H:%M:%S')
  if [ "$code" = "200" ]; then
    echo "OK  $ts  http=$code health=$health restarts=$restarts"
    pass=$((pass + 1))
  else
    echo "FAIL $ts  http=$code health=$health restarts=$restarts"
    fail=$((fail + 1))
  fi
  sleep "$INTERVAL"
done

end_restarts=$(docker inspect "$NAME" --format '{{.RestartCount}}')
echo "RestartCount: $start_restarts -> $end_restarts"
echo "=== result: $pass ok, $fail fail ==="
exit $fail
