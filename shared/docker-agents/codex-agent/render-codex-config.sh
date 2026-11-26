#!/bin/bash
# 生成容器内 ~/.codex/config.toml
# 旧栈（python/lib）已于 B7 移除，此处调用新栈 python/tools 下的等价实现。
set -euo pipefail
exec python3 "${MAILBUS_PY_ROOT:-/mailbus/python}/tools/codex_config_render.py"
