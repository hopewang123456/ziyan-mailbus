#!/bin/bash
# 子言 AI 团队 Docker 停止 — 委托 Python mailbus CLI
set -uo pipefail
COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIL_DIR="$(cd "${COMPOSE_DIR}/.." && pwd)"
exec python3 "${MAIL_DIR}/tools/mailbus.py" stop "$@"
