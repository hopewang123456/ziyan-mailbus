#!/bin/bash
# 灵巡巡检 cron — 每15分钟向灵巡发送巡检指令
# 由 mailbus 的 bus.py send 命令实现

cd /mnt/e/ai_tools/mail
python3 bus.py send lingxun \
  --msg "⏰ 执行定时巡检 — 请检查所有Agent inbox状态、任务进度，生成巡检报告。回复给发件人 mailbus。" \
  --from mailbus \
  --priority normal \
  --type task \
  --data-dir /mnt/e/ai_tools/mail/store >> /mnt/e/ai_tools/mail/store/lingxun-patrol.log 2>&1
