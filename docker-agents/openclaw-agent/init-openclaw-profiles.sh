#!/bin/bash
# 为 xiaoqi / yige 生成独立 OpenClaw 状态目录 — 委托 Python
set -euo pipefail
ROOT="${MAILBUS_ROOT:-/mailbus}"
cd "$ROOT"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m lib.adapters.container.openclaw_profiles
