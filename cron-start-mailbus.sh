#!/bin/bash
# ============================================================
# cron-start-mailbus.sh — 由 crontab/系统服务调用
# 现在委托给 mailbus-boot.sh 全量启动（含所有 agent）
# ============================================================
exec /mnt/e/ai_tools/mail/mailbus-boot.sh

