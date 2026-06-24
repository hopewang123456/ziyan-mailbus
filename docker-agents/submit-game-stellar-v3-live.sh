#!/bin/bash
# v3 LIVE 验收 — 入口脚本（委托 mailbus 容器执行，避免 Windows 挂载权限问题）
set -euo pipefail
exec docker exec docker-agents-mailbus-1 bash /mailbus/docker-agents/submit-game-stellar-v3-live-docker.sh "$@"
