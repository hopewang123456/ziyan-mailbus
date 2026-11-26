#!/bin/bash
# 为各 openclaw agent 生成独立 OpenClaw 状态目录
# 旧栈（python/lib）已于 B7 移除，此处调用新栈 python/tools 下的等价实现。
set -euo pipefail
exec python3 "${MAILBUS_PY_ROOT:-/mailbus/python}/tools/openclaw_profiles_init.py"
