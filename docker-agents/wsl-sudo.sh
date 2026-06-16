#!/bin/bash
# WSL 下带密码的 sudo（密码来自 .env.secrets，勿提交仓库）
set -euo pipefail
COMPOSE_DIR="$(cd "$(dirname "$0")" && pwd)"
SECRETS="$COMPOSE_DIR/.env.secrets"
if [ -f "$SECRETS" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$SECRETS"
  set +a
fi
if [ -z "${SUDO_PASSWORD:-}" ]; then
  echo "[wsl-sudo] 缺少 SUDO_PASSWORD，请创建 $SECRETS（见 .env.secrets.example）" >&2
  exit 1
fi
printf '%s\n' "$SUDO_PASSWORD" | sudo -S "$@"
