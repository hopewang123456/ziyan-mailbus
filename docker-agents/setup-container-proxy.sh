#!/bin/bash
# 根据 Windows 系统代理开关，为 Docker 容器写入 HTTP(S)_PROXY。
# Clash 系统代理开 → 走 Windows 宿主机 :7897；关 → 直连（不走失效的 172.17.0.1:7898）。
set -euo pipefail

COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${COMPOSE_DIR}/.env"
WIN_HOST="$(ip route show default 2>/dev/null | awk '{print $3}' | head -1)"
CLASH_PORT="${CLASH_PORT:-7897}"
PS="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"

proxy_enable=0
if [ -x "$PS" ]; then
  proxy_enable="$("$PS" -NoProfile -Command \
    "(Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings').ProxyEnable" \
    2>/dev/null | tr -d '\r\n' || echo 0)"
fi

container_proxy=""
if [ "${proxy_enable}" = "1" ] && [ -n "${WIN_HOST}" ]; then
  if curl -s -o /dev/null --connect-timeout 3 \
    -x "http://${WIN_HOST}:${CLASH_PORT}" \
    "https://api.deepseek.com/v1/models" >/dev/null 2>&1; then
    container_proxy="http://${WIN_HOST}:${CLASH_PORT}"
  fi
fi

upsert_env() {
  local key="$1" value="$2" file="$3"
  if [ -f "$file" ] && grep -q "^${key}=" "$file"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$file"
  else
    echo "${key}=${value}" >> "$file"
  fi
}

touch "$ENV_FILE"
upsert_env "CONTAINER_HTTP_PROXY" "$container_proxy" "$ENV_FILE"
upsert_env "CONTAINER_HTTPS_PROXY" "$container_proxy" "$ENV_FILE"

if [ -n "$container_proxy" ]; then
  echo "[proxy] Windows system proxy ON → containers use ${container_proxy}"
else
  echo "[proxy] Windows system proxy OFF or Clash unreachable → containers use direct connection"
fi

echo "$container_proxy" > "${COMPOSE_DIR}/.proxy-state"
