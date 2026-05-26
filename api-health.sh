#!/bin/bash
# api-health.sh — mailbus API Server 健康检查与自动重启
# 用 crontab 每隔5分钟运行一次

DATA_DIR="/mnt/e/ai_tools/mail"
HOST="0.0.0.0"
PORT=9812
LOG_FILE="$DATA_DIR/logs/api-health.log"

# 检查 API 是否响应
curl -s -o /dev/null -w "%{http_code}" "http://${HOST}:${PORT}/api/status" \
    --connect-timeout 5 --max-time 10 2>/dev/null | grep -q "200"

if [ $? -ne 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ API 无响应，尝试重启..." >> "$LOG_FILE"
    # 杀旧进程
    PID=$(pgrep -f "bus.py serve" 2>/dev/null)
    if [ -n "$PID" ]; then
        kill "$PID" 2>/dev/null
        sleep 2
        kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null
    fi
    # 重启
    cd "$DATA_DIR" && nohup python3 bus.py serve --host "$HOST" --port "$PORT" \
        --data-dir "${DATA_DIR}/store" >> "${DATA_DIR}/store/cron.log" 2>&1 &
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ API 已重启 (PID: $!)" >> "$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ API 正常" >> "$LOG_FILE"
fi
