#!/bin/bash
# 确保 Hermes 容器内 6 个编制 dashboard 全部就绪（lingtuo/lingzhang 等）
set -euo pipefail

CONTAINER="${HERMES_CONTAINER:-docker-agents-hermes-1}"
PYTHON="${HERMES_PYTHON:-python3.12}"
CLI=( "$PYTHON" -m hermes_cli.main -p default dashboard )

# profile port（与 ORGANIZATION.md / entrypoint.sh 一致）
DASHBOARDS=(
  "lingzhao:9120"
  "lingjin:9121"
  "lingxi:9122"
  "lingxun:9125"
  "lingtuo:9126"
  "lingzhang:9127"
)

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "[ensure-hermes] container $CONTAINER not running — skip"
  exit 0
fi

_failures=0

_ensure_one() {
  local profile="$1" port="$2"
  local code
  code=$(docker exec "$CONTAINER" curl -s -o /dev/null -w '%{http_code}' \
    --connect-timeout 3 "http://127.0.0.1:${port}/" 2>/dev/null || echo "000")
  if [[ "$code" == "200" || "$code" == "301" || "$code" == "302" ]]; then
    echo "[ensure-hermes] OK  ${profile}:${port} (${code})"
    return 0
  fi

  echo "[ensure-hermes] START ${profile}:${port} (was ${code})..."
  docker exec -d "$CONTAINER" bash -lc \
    "nohup ${CLI[*]} --port ${port} --host 0.0.0.0 --open-profile ${profile} --insecure --skip-build \
      >/tmp/hermes-dash-${profile}.log 2>&1 &"

  local i code2
  for i in $(seq 1 15); do
    sleep 2
    code2=$(docker exec "$CONTAINER" curl -s -o /dev/null -w '%{http_code}' \
      --connect-timeout 3 "http://127.0.0.1:${port}/" 2>/dev/null || echo "000")
    if [[ "$code2" == "200" || "$code2" == "301" || "$code2" == "302" ]]; then
      echo "[ensure-hermes] OK  ${profile}:${port} ready after ${i} tries"
      return 0
    fi
  done

  echo "[ensure-hermes] FAIL ${profile}:${port} — log tail:"
  docker exec "$CONTAINER" tail -5 "/tmp/hermes-dash-${profile}.log" 2>/dev/null || true
  _failures=$((_failures + 1))
  return 1
}

echo "[ensure-hermes] checking dashboards in $CONTAINER ..."
for spec in "${DASHBOARDS[@]}"; do
  _ensure_one "${spec%%:*}" "${spec##*:}" || true
done

if [[ "$_failures" -gt 0 ]]; then
  echo "[ensure-hermes] $_failures dashboard(s) failed"
  exit 1
fi
echo "[ensure-hermes] all dashboards OK"
exit 0
