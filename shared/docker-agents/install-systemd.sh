#!/bin/bash
# 安装/更新 systemd 单元（需 root）
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAILBUS_ROOT="$(cd "${DIR}/.." && pwd)"
MAILBUS_USER="${SUDO_USER:-${USER:-root}}"

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 root 运行: sudo bash $0"
  exit 1
fi

sed -e "s|@MAILBUS_ROOT@|${MAILBUS_ROOT}|g" \
    -e "s|@MAILBUS_USER@|${MAILBUS_USER}|g" \
    "$DIR/docker-agents.service" > /etc/systemd/system/docker-agents.service
chmod 644 /etc/systemd/system/docker-agents.service

mkdir -p /etc/systemd/system/docker.service.d
if grep -q 'post-start.sh' /etc/systemd/system/docker.service.d/override.conf 2>/dev/null; then
  install -m 644 "$DIR/docker.service.d-override.conf" /etc/systemd/system/docker.service.d/override.conf
  echo "[install] 已移除 docker.service ExecStartPost post-start.sh"
fi

systemctl daemon-reload
echo "[install] docker-agents.service 已更新 @ ${MAILBUS_ROOT}（ExecStop 不再 compose down）"
systemctl is-enabled docker-agents.service >/dev/null 2>&1 && echo "[install] docker-agents: enabled" || echo "[install] docker-agents: not enabled"
