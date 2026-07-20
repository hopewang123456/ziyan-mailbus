#!/bin/bash
# WSL 启动后：按 Windows 系统代理状态刷新容器代理配置
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAILBUS_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
python3 "${MAILBUS_ROOT}/tools/mailbus.py" proxy setup

# 旧版 socat 会把流量转到 WSL 127.0.0.1:7897（Clash 在 Windows 上时无效），停掉以免误导
pkill -f "socat.*7898" 2>/dev/null || true
