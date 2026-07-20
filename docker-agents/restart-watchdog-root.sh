#!/bin/bash
# 以 root 运行：清理旧 watchdog + 修复 launch queue 权限

PATTERN="/mnt/e/ai_tools/mail/docker-agents/mailbus-launch-watchdog.sh"

for pid in $(pgrep -f "$PATTERN" 2>/dev/null); do
  kill "$pid" 2>/dev/null || true
done
sleep 1

QDIR="/mnt/e/ai_tools/mail/run/launch-queue"
export MAILBUS_LAUNCH_QUEUE="$QDIR"
mkdir -p "$QDIR"
chmod 777 "$QDIR" 2>/dev/null || true
echo "[watchdog-root] queue ready at $QDIR, stale watchdogs cleared"
