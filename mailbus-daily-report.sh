#!/bin/bash
# ============================================================
# mailbus-daily-report.sh — 灵巡日报生成触发器
# 
# 每天 23:30 执行：触发灵巡生成当日巡检日报
# 日报写入 store/reports/daily/<date>.md
# ============================================================

MAIL_DIR="/mnt/e/ai_tools/mail"
DATA_DIR="$MAIL_DIR/store"

cd "$MAIL_DIR" || exit 1

TODAY=$(date '+%Y-%m-%d')

# 发送日报生成任务给灵巡
python3 mailbus-send \
  --to lingxun \
  --from mailbus \
  --type task \
  --priority low \
  --content "📊 生成日报 — 今天是 $TODAY。请汇总今日巡检结果，生成日报写入 store/reports/daily/$TODAY.md。内容包括：整体概览（消息总数/完成数/超时数）、Agent活跃度统计、需要关注的问题。"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ 灵巡日报任务已发送 ($TODAY)" >> "$DATA_DIR/cron.log"
