#!/bin/bash
# Mailbus Linux 启动脚本（薄包装 → python tools/mailbus.py start）
# 前提：python3 ≥ 3.11 且在 PATH；本仓库任意位置均可执行。
set -euo pipefail

# 定位仓库根目录（本脚本位于 <root>/scripts/）
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ ! -f "$ROOT/tools/mailbus.py" ]; then
  echo "[ERROR] mailbus root not found: $ROOT"
  echo "        Place this repo anywhere and run scripts/start-mailbus.sh from it." >&2
  exit 1
fi

cd "$ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 not found — install Python >= 3.11 first." >&2
  exit 1
fi

echo "=========================================="
echo "  mailbus"
echo "  API: http://localhost:9814/"
echo "=========================================="

python3 tools/mailbus.py start
