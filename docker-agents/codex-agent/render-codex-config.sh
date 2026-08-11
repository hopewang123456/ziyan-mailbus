#!/bin/bash
# 生成容器内 ~/.codex/config.toml — 委托 Python lib.adapters.container.codex_config
set -euo pipefail
ROOT="${MAILBUS_ROOT:-/mailbus}"
cd "$ROOT"
exec python3 -m lib.adapters.container.codex_config
