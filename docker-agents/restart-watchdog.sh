#!/bin/bash
# 重启 mailbus CLI watchdog — 只保留一个实例（优先走 systemd）

WATCHDOG="/mnt/e/ai_tools/mail/docker-agents/mailbus-launch-watchdog.sh"
PATTERN="/mnt/e/ai_tools/mail/docker-agents/mailbus-launch-watchdog.sh"

run_in_wsl() {
  if [ -f /proc/version ] && grep -qi microsoft /proc/version 2>/dev/null; then
    "$@"
  else
    /mnt/c/Windows/System32/wsl.exe -d Ubuntu -u root -e "$@"
  fi
}

# 修复 launch queue 权限（非 root 时 chmod 可能失败，忽略）
run_in_wsl bash -c 'mkdir -p /tmp/mailbus-launch-queue && (chmod 1777 /tmp/mailbus-launch-queue 2>/dev/null || true)'

if run_in_wsl systemctl is-enabled mailbus-watchdog >/dev/null 2>&1; then
  # 已在运行则跳过 restart，避免无意义 bounce
  if run_in_wsl systemctl is-active mailbus-watchdog >/dev/null 2>&1; then
    count=$(pgrep -f "$PATTERN" 2>/dev/null | wc -l)
    echo "Watchdog already running via systemd (instances: $count)"
    exit 0
  fi
  run_in_wsl systemctl start mailbus-watchdog
  sleep 1
  if run_in_wsl systemctl is-active mailbus-watchdog >/dev/null 2>&1; then
    count=$(pgrep -f "$PATTERN" 2>/dev/null | wc -l)
    echo "Watchdog started via systemd (instances: $count)"
    exit 0
  fi
  echo "ERROR: systemd mailbus-watchdog failed to start" >&2
  exit 1
fi

# 无 systemd 时回退：清理 + 单个 nohup
run_in_wsl bash /mnt/e/ai_tools/mail/restart-watchdog-root.sh
nohup bash "$WATCHDOG" >>/tmp/mailbus-watchdog.log 2>&1 &
sleep 1
count=$(pgrep -f "$PATTERN" 2>/dev/null | wc -l)
if [ "$count" -eq 1 ]; then
  echo "Watchdog restarted (PID: $(pgrep -f "$PATTERN"))"
  tail -1 /tmp/mailbus-watchdog.log
else
  echo "WARN: expected 1 watchdog, found $count" >&2
  pgrep -af "$PATTERN" >&2 || true
  exit 1
fi
