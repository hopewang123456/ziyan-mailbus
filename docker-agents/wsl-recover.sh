#!/bin/bash
# WSL 轻量恢复 — 委托 Python mailbus CLI
# FULL=1 / SCAN=0 仍可通过环境变量 + recover full --no-scan 使用
set -uo pipefail
COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIL_DIR="$(cd "${COMPOSE_DIR}/.." && pwd)"
PY=(python3 "${MAIL_DIR}/tools/mailbus.py" recover)
if [ "${FULL:-0}" = "1" ]; then
  exec "${PY[@]}" full $( [ "${SCAN:-1}" = "0" ] && echo --no-scan )
fi
exec "${PY[@]}" quick $( [ "${SCAN:-1}" = "0" ] && echo --no-scan )
