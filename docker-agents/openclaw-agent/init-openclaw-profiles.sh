#!/bin/bash
# 为 xiaoqi / yige 生成独立 OpenClaw 状态目录 — 委托 Python
set -euo pipefail
ROOT="${MAILBUS_ROOT:-/mailbus}"
cd "$ROOT"
exec python3 -m lib.container.openclaw_profiles
