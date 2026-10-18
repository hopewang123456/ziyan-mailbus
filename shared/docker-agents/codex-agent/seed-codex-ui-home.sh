#!/bin/bash
# codexapp 新建对话默认落在 $HOME/Documents/Codex（Desktop 兼容路径）。
# 容器内常以 root 运行，若 HOME=/root 则读不到 /home/node/.codex 的人设配置。
set -euo pipefail

CODEX_HOME="${CODEX_HOME:-/home/node/.codex}"
AGENT="${CODEX_AGENT:-codex}"
PROJECT_DIR="${CODEX_PROJECT_DIR:-/home/node/agent-workspace/${AGENT}}"
APP_HOME="${CODEX_APP_HOME:-/home/node}"

mkdir -p "$APP_HOME" "$CODEX_HOME" "${APP_HOME}/Documents/Codex" "${PROJECT_DIR}/.codex"

if [ "$(id -u)" = "0" ] && [ ! -e /root/.codex ]; then
  ln -sfn "$CODEX_HOME" /root/.codex
fi

if [ -f "${CODEX_HOME}/config.toml" ]; then
  mkdir -p "${APP_HOME}/Documents/Codex/.codex"
  cp -f "${CODEX_HOME}/config.toml" "${APP_HOME}/Documents/Codex/.codex/config.toml"
fi

if [ -f "${PROJECT_DIR}/AGENTS.md" ]; then
  cp -f "${PROJECT_DIR}/AGENTS.md" "${APP_HOME}/Documents/Codex/AGENTS.md"
fi

# 兼容 root 下仍走 Documents/Codex 的路径
if [ "$(id -u)" = "0" ] && [ "$APP_HOME" != "/root" ]; then
  mkdir -p /root/Documents
  if [ ! -e /root/Documents/Codex ]; then
    ln -sfn "${APP_HOME}/Documents/Codex" /root/Documents/Codex
  fi
fi
