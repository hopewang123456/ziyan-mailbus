#!/bin/bash
# WSL 启动后：按 Windows 系统代理状态刷新容器代理配置（不再依赖失效的 172.17.0.1:7898 socat）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "${SCRIPT_DIR}/setup-container-proxy.sh"

# 旧版 socat 会把流量转到 WSL 127.0.0.1:7897（Clash 在 Windows 上时无效），停掉以免误导
pkill -f "socat.*7898" 2>/dev/null || true
