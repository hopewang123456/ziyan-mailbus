#!/bin/bash
# 以 root 运行：清理旧 watchdog + 修复 launch queue 权限

PATTERN="/mnt/e/ai_tools/mail/mailbus-launch-watchdog.sh"

for pid in $(pgrep -f "$PATTERN" 2>/dev/null); do
  kill "$pid" 2>/dev/null || true
done
sleep 1

mkdir -p /tmp/mailbus-launch-queue
chmod 1777 /tmp/mailbus-launch-queue 2>/dev/null || true
echo "[watchdog-root] queue ready, stale watchdogs cleared"
