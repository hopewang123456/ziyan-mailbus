#!/bin/bash
# 移除 WSL 宿主机全部 mailbus 相关 crontab（改由 mailbus 容器内置 SchedulerHub 负责）
set -euo pipefail

TMP="$(mktemp)"
crontab -l 2>/dev/null > "$TMP" || true

# 匹配 mailbus / mailbox-daemon / 旧 scan-bridge / 宿主机 serve / 日志清理 等条目
MAILBUS_CRON_RE='python3 -m bus (scan|serve)|bus\.py (scan|serve)|mailbus-memory-bridge|mailbox-daemon|daemon-manager|api-health\.sh|mailbus-patrol-cron|cron-lingxun-patrol|mailbus-daily-report|cron-start-mailbus|mailbus-boot|mailbus-review-cron|/ai_tools/mail/logs.*-mtime|find /mnt/e/ai_tools/mail/logs'

# 去掉 mailbus 相关注释行（避免留下空壳说明）
COMMENT_RE='^#.*(mailbus|Mailbox Daemon|mailbox-daemon|memory-bridge|api-health|mailbus-boot|清理旧日志|mail/logs)'

if grep -qE "$MAILBUS_CRON_RE|$COMMENT_RE" "$TMP" 2>/dev/null; then
  grep -vE "$MAILBUS_CRON_RE|$COMMENT_RE" "$TMP" > "${TMP}.new" || true
  # 去掉连续空行
  awk 'NF || prev {print; prev=NF}' "${TMP}.new" > "${TMP}.final" || cp "${TMP}.new" "${TMP}.final"
  if [ -s "${TMP}.final" ]; then
    crontab "${TMP}.final"
    echo "[uninstall-cron] 已移除 mailbus 相关 WSL cron，保留其它条目"
  else
    crontab -r 2>/dev/null || true
    echo "[uninstall-cron] 已清空 crontab（仅剩 mailbus 条目）"
  fi
else
  echo "[uninstall-cron] 无需清理（无 mailbus WSL cron 条目）"
fi

rm -f "$TMP" "${TMP}.new" "${TMP}.final"
