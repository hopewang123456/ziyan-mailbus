#!/bin/bash
# mailbus-launch-watchdog.sh v13 — WSL 终端弹窗 Watchdog
# 用 PowerShell Start-Process 弹新 WSL 窗口（提供完整 TTY 给 docker exec -it）

QUEUE_DIR="/tmp/mailbus-launch-queue"
mkdir -p "$QUEUE_DIR"

PS_EXE="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
WINDOWS_CMD="/mnt/c/Windows/System32/cmd.exe"
# cmd.exe 只认 Windows 路径，/mnt/c/... 会导致 start 把标题当成可执行文件
WSL_WIN='C:\Windows\System32\wsl.exe'

echo "[mailbus-watchdog] v13 启动，监听 $QUEUE_DIR ..."

launch_one() {
  local file="$1"
  local cmd title
  cmd=$(sed -n '1p' "$file")
  title=$(sed -n '2p' "$file")
  ts=$(date +%s)
  title="${title:-Agent}"

  local wrapper="/tmp/launch-ps-wrapper-${ts}.sh"
  cat > "$wrapper" <<WRAP
#!/bin/bash
cd /mnt/e
${cmd}
echo ""
echo "--- ${title} 执行完毕 ---"
echo "按 Enter 关闭..."
read
WRAP
  chmod +x "$wrapper"

  if [ -x "$PS_EXE" ]; then
    # 主路径：PowerShell Start-Process（不依赖 cmd PATH，不会误解析 start 标题）
    "$PS_EXE" -NoProfile -Command \
      "Start-Process -FilePath '${WSL_WIN}' -ArgumentList '-d','Ubuntu','-e','bash','${wrapper}'" \
      >/dev/null 2>&1 &
    echo "[mailbus-watchdog] v13 已启动: $title"
  elif [ -x "$WINDOWS_CMD" ]; then
    # 回退：cmd start "" + Windows 路径（标题必须留空 ""）
    "$WINDOWS_CMD" /c start "" "${WSL_WIN}" -d Ubuntu -e bash "${wrapper}" >/dev/null 2>&1 &
    echo "[mailbus-watchdog] v13 (cmd) 已启动: $title"
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
