#!/bin/bash
# Run inside docker-agents-hermes-1 (or any Hermes container).
set -euo pipefail

export HOME=/home/hermes
export HERMES_HOME=/home/hermes/.hermes
export PATH="/usr/local/bin:/usr/bin:$PATH"

echo "[memos] HOME=$HOME HERMES_HOME=$HERMES_HOME"
echo "[memos] node=$(node -v) npm=$(npm -v)"

# Non-interactive Hermes-only install from official installer
curl -fsSL "https://raw.githubusercontent.com/MemTensor/MemOS/main/apps/memos-local-plugin/install.sh" \
  -o /tmp/memos-install.sh
chmod +x /tmp/memos-install.sh

# Force hermes target; no TTY → auto path also hermes when only hermes present
bash /tmp/memos-install.sh --agent hermes

echo "[memos] install finished"
echo "[memos] memory status:"
hermes memory status || true

echo "[memos] tree:"
ls -la "$HERMES_HOME/plugins/memory" 2>/dev/null || true
ls -la "$HERMES_HOME/memos-plugin" 2>/dev/null || true
ls -la "$HERMES_HOME/plugins/memos-local-plugin" 2>/dev/null || ls -la "$HOME/.hermes/plugins" 2>/dev/null || true
