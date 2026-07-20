#!/bin/bash
# 从 mailbus Web 看板启动指定 agent — 委托 Python launch_agent
set -euo pipefail
OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAIL_DIR="$(cd "${OPS_DIR}/../.." && pwd)"
exec python3 "${MAIL_DIR}/tools/ops/launch_agent.py" "$@"
