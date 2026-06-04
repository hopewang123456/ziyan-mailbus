#!/bin/bash
# ============================================================
# mailbus-patrol-cron.sh — 灵巡定时巡检
# 
# 每15分钟执行一次：向灵巡(lingxun)发送巡检任务
# 灵巡收到后自动执行巡检并生成报告
# ============================================================

MAIL_DIR="/mnt/e/ai_tools/mail"
DATA_DIR="$MAIL_DIR/store"

cd "$MAIL_DIR" || exit 1

# 发送巡检任务给灵巡
python3 mailbus-send \
  --to lingxun \
  --from mailbus \
  --type task \
  --priority normal \
  --content "⏰ 执行定时巡检 — 请检查所有Agent inbox状态、任务进度，生成巡检报告。回复给发件人 mailbus。"

# 记录日志
echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ 灵巡巡检任务已发送" >> "$DATA_DIR/cron.log"
