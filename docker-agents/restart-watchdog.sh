#!/bin/bash
# 重启 mailbus CLI watchdog — 只保留一个实例（优先 systemd，失败则 nohup，不阻塞 start-team）

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MAILBUS_ROOT="${MAILBUS_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"

WATCHDOG="${MAILBUS_ROOT}/docker-agents/mailbus-launch-watchdog.sh"
PATTERN="${MAILBUS_ROOT}/docker-agents/mailbus-launch-watchdog.sh"
SERVICE_UNIT="${MAILBUS_ROOT}/docker-agents/mailbus-watchdog.service"

run_in_wsl() {
  if [ -f /proc/version ] && grep -qi microsoft /proc/version 2>/dev/null; then
    "$@"
  else
    /mnt/c/Windows/System32/wsl.exe -d Ubuntu -e "$@"
  fi
}

systemd_exec_ok() {
  local execstart
  execstart="$(run_in_wsl systemctl show mailbus-watchdog -p ExecStart --value 2>/dev/null || true)"
  [[ "$execstart" == *"docker-agents/mailbus-launch-watchdog.sh"* ]]
}

try_systemd_watchdog() {
  run_in_wsl systemctl is-enabled mailbus-watchdog >/dev/null 2>&1 || return 1
  if ! systemd_exec_ok; then
    echo "WARN: mailbus-watchdog.service ExecStart 路径过期（缺 docker-agents/）" >&2
    echo "      修复: sudo bash ${MAILBUS_ROOT}/docker-agents/install-mailbus-watchdog-service.sh" >&2
    return 1
  fi
  if run_in_wsl systemctl is-active mailbus-watchdog >/dev/null 2>&1; then
    count=$(pgrep -f "$PATTERN" 2>/dev/null | wc -l)
    echo "Watchdog already running via systemd (instances: $count)"
    return 0
  fi
  # 非交互启动：先试 sudo -n，再试直接 start（root WSL 会话）
  if run_in_wsl sudo -n systemctl start mailbus-watchdog 2>/dev/null \
    || run_in_wsl systemctl start mailbus-watchdog 2>/dev/null; then
    sleep 1
    if run_in_wsl systemctl is-active mailbus-watchdog >/dev/null 2>&1; then
      count=$(pgrep -f "$PATTERN" 2>/dev/null | wc -l)
      echo "Watchdog started via systemd (instances: $count)"
      return 0
    fi
  fi
  echo "WARN: systemd mailbus-watchdog 无法非交互启动（需 sudo 或修复 unit）" >&2
  return 1
}

start_nohup_watchdog() {
  run_in_wsl bash "${MAILBUS_ROOT}/docker-agents/restart-watchdog-root.sh" 2>/dev/null || true
  for pid in $(pgrep -f "$PATTERN" 2>/dev/null); do
    kill "$pid" 2>/dev/null || true
  done
  sleep 1
  QDIR="${MAILBUS_LAUNCH_QUEUE:-${MAILBUS_ROOT}/run/launch-queue}"
  mkdir -p "$QDIR"
  chmod 777 "$QDIR" 2>/dev/null || true
  nohup bash "$WATCHDOG" >>/tmp/mailbus-watchdog.log 2>&1 &
  sleep 1
  count=$(pgrep -f "$PATTERN" 2>/dev/null | wc -l)
  if [ "$count" -ge 1 ]; then
    echo "Watchdog started via nohup (instances: $count, log: /tmp/mailbus-watchdog.log)"
    tail -1 /tmp/mailbus-watchdog.log 2>/dev/null || true
    return 0
  fi
  echo "WARN: nohup watchdog failed to start" >&2
  pgrep -af "$PATTERN" >&2 || true
  return 1
}

if try_systemd_watchdog; then
  exit 0
fi

start_nohup_watchdog
exit $?
