#!/bin/bash
# mailbus-launch-watchdog.sh v15 — WSL launch queue
# background：Hidden（pusher/scan 无弹窗）；interactive：可见 WSL 窗口（docker exec -it 需 TTY）

MAILBUS_ROOT="${MAILBUS_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
QUEUE_DIR="${MAILBUS_LAUNCH_QUEUE:-${MAILBUS_ROOT}/run/launch-queue}"
mkdir -p "$QUEUE_DIR"
chmod 777 "$QUEUE_DIR" 2>/dev/null || true

PS_EXE="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
WINDOWS_CMD="/mnt/c/Windows/System32/cmd.exe"
# cmd.exe 只认 Windows 路径，/mnt/c/... 会导致 start 把标题当成可执行文件
WSL_WIN='C:\Windows\System32\wsl.exe'

echo "[mailbus-watchdog] v15 启动，监听 $QUEUE_DIR ..."

_launch_mode_for() {
  local cmd="$1" mode="$2"
  mode="${mode:-background}"
  if [ "$mode" = "interactive" ]; then
    echo interactive
    return
  fi
  if echo "$cmd" | grep -qE 'docker exec -it|openclaw tui|-NoExit|powershell.*NoExit'; then
    echo interactive
    return
  fi
  echo background
}

launch_one() {
  local file="$1"
  local cmd title mode launch_mode
  cmd=$(sed -n '1p' "$file")
  title=$(sed -n '2p' "$file")
  mode=$(sed -n '3p' "$file")
  ts=$(date +%s)
  title="${title:-Agent}"
  launch_mode=$(_launch_mode_for "$cmd" "$mode")

  if [ "$launch_mode" = "interactive" ]; then
    local vis_script="/tmp/launch-interactive-${ts}.sh"
    cat > "$vis_script" <<WRAP
#!/bin/bash
set +e
cd /mnt/e
${cmd}
EXIT_CODE=\$?
echo ""
if [ \$EXIT_CODE -ne 0 ]; then
  echo "⚠️  脚本异常退出 (code: \$EXIT_CODE)"
else
  echo "✅ 脚本执行完毕 (code: \$EXIT_CODE)"
fi
echo "--- ${title} 执行完毕 \$(date) ---" >> /tmp/mailbus-launch.log 2>&1
echo "按 Enter 键关闭窗口..."
read
WRAP
    chmod +x "$vis_script"
    if [ -x "$PS_EXE" ]; then
      # interactive：可见 WSL 窗口（docker exec -it / hermes chat 需要 TTY）
      "$PS_EXE" -NoProfile -Command \
        "Start-Process -FilePath '${WSL_WIN}' -ArgumentList '-d','Ubuntu','-e','bash','${vis_script}'" \
        >/dev/null 2>&1 &
      echo "[mailbus-watchdog] v15 已启动(interactive): $title"
    elif [ -x "$WINDOWS_CMD" ]; then
      "$WINDOWS_CMD" /c start "" "${WSL_WIN}" -d Ubuntu -e bash "${vis_script}" >/dev/null 2>&1 &
      echo "[mailbus-watchdog] v15 (cmd) 已启动(interactive): $title"
    else
      echo "[mailbus-watchdog] ERROR: 找不到 PowerShell 或 cmd.exe" >&2
    fi
    rm -f "$file" 2>/dev/null || true
    return
  fi

  local wrapper="/tmp/launch-ps-wrapper-${ts}.sh"
  cat > "$wrapper" <<WRAP
#!/bin/bash
cd /mnt/e
${cmd}
echo "--- ${title} 执行完毕 $(date) ---" >> /tmp/mailbus-launch.log 2>&1
WRAP
  chmod +x "$wrapper"

  if [ -x "$PS_EXE" ]; then
    # background：Hidden，避免 pusher/scan 闪黑控制台
    "$PS_EXE" -NoProfile -Command \
      "Start-Process -WindowStyle Hidden -FilePath '${WSL_WIN}' -ArgumentList '-d','Ubuntu','-e','bash','${wrapper}'" \
      >/dev/null 2>&1 &
    echo "[mailbus-watchdog] v15 已启动(background): $title"
  elif [ -x "$WINDOWS_CMD" ]; then
    "$WINDOWS_CMD" /c start /min "" "${WSL_WIN}" -d Ubuntu -e bash "${wrapper}" >/dev/null 2>&1 &
    echo "[mailbus-watchdog] v15 (cmd) 已启动(background): $title"
  else
    echo "[mailbus-watchdog] ERROR: 找不到 PowerShell 或 cmd.exe" >&2
  fi

  rm -f "$file" 2>/dev/null || true
}

while true; do
  for file in "$QUEUE_DIR"/*.launch; do
    [ -f "$file" ] || continue
    # 原子抢占：只有一个 watchdog 能 mv 成功，避免双实例各弹一窗
    processing="${file}.$$.processing"
    if ! mv "$file" "$processing" 2>/dev/null; then
      continue
    fi
    launch_one "$processing"
  done
  sleep 1
done
