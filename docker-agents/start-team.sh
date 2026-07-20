#!/bin/bash
# 兼容入口：委托 mail/tools/mailbus.py start
set -uo pipefail
COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAILBUS_ROOT="${MAILBUS_ROOT:-$(cd "${COMPOSE_DIR}/.." && pwd)}"
if [ ! -f "${MAILBUS_ROOT}/tools/mailbus.py" ]; then
  echo "mail not found — set MAILBUS_ROOT" >&2
  exit 1
fi
exec python3 "${MAILBUS_ROOT}/tools/mailbus.py" start "$@"
