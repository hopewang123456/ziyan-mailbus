#!/bin/bash
# ============================================================
# wsl-terminal-bridge.sh — 从 WSL 弹 Windows 终端窗口
# 由 mailbus 容器通过 docker socket 调用
# 用法: docker exec <host-wsl> bash /mnt/e/ai_tools/mail/wsl-terminal-bridge.sh "<命令>" "<窗口标题>"
# ============================================================
CMD="$1"
TITLE="${2:-子言AI Agent}"

set +e

PS_EXE="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
WINDOWS_CMD="/mnt/c/Windows/System32/cmd.exe"
WSL_WIN='C:\Windows\System32\wsl.exe'

if [ -x "$PS_EXE" ]; then
  "$PS_EXE" -NoProfile -Command \
    "Start-Process -FilePath '${WSL_WIN}' -ArgumentList '-d','Ubuntu','-e','bash','-c','${CMD}; echo; echo 按 Enter 关闭...; read'" \
    >/dev/null 2>&1
  exit 0
fi

if [ -x "$WINDOWS_CMD" ]; then
  "$WINDOWS_CMD" /c start "" "${WSL_WIN}" -d Ubuntu -e bash -c "$CMD; echo; echo '按 Enter 关闭...'; read"
  exit 0
fi

# 方法3: 回退 - 直接执行
echo "[WARN] 无法弹窗，直接执行命令"
eval "$CMD"
exit $?
