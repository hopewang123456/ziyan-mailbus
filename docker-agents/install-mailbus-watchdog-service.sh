#!/bin/bash
# 安装/更新 mailbus-watchdog systemd 单元（需 root：sudo bash install-mailbus-watchdog-service.sh）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAILBUS_ROOT="$(cd "${ROOT}/.." && pwd)"
MAILBUS_LAUNCH_QUEUE="${MAILBUS_LAUNCH_QUEUE:-${MAILBUS_ROOT}/run/launch-queue}"
UNIT_SRC="${ROOT}/mailbus-watchdog.service"
UNIT_DST="/etc/systemd/system/mailbus-watchdog.service"

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 root 运行: sudo bash $0" >&2
  exit 1
fi

if [ ! -f "$UNIT_SRC" ]; then
  echo "missing $UNIT_SRC" >&2
  exit 1
fi

sed -e "s|@MAILBUS_ROOT@|${MAILBUS_ROOT}|g" \
    -e "s|@MAILBUS_LAUNCH_QUEUE@|${MAILBUS_LAUNCH_QUEUE}|g" \
    "$UNIT_SRC" > "$UNIT_DST"
chmod 644 "$UNIT_DST"
systemctl daemon-reload
systemctl enable mailbus-watchdog.service
systemctl restart mailbus-watchdog.service
sleep 1
systemctl --no-pager status mailbus-watchdog.service || true
echo "[install] mailbus-watchdog @ ${MAILBUS_ROOT}"
