#!/bin/bash
# 安装/更新 systemd 单元（需 root）
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 root 运行: sudo bash $0"
  exit 1
fi

install -m 644 "$DIR/docker-agents.service" /etc/systemd/system/docker-agents.service

mkdir -p /etc/systemd/system/docker.service.d
if grep -q 'post-start.sh' /etc/systemd/system/docker.service.d/override.conf 2>/dev/null; then
  install -m 644 "$DIR/docker.service.d-override.conf" /etc/systemd/system/docker.service.d/override.conf
  echo "[install] 已移除 docker.service ExecStartPost post-start.sh"
fi

systemctl daemon-reload
echo "[install] docker-agents.service 已更新（ExecStop 不再 compose down）"
systemctl is-enabled docker-agents.service >/dev/null 2>&1 && echo "[install] docker-agents: enabled" || echo "[install] docker-agents: not enabled"
