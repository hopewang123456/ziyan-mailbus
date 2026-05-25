#!/bin/bash
# daemon-manager.sh — Mailbox Daemon 部署管理脚本
# 用法:
#   ./daemon-manager.sh start             启动所有 agent 的 daemon
#   ./daemon-manager.sh start lingxiao    启动指定 agent
#   ./daemon-manager.sh stop              停止所有
#   ./daemon-manager.sh stop lingxiao     停止指定
#   ./daemon-manager.sh status            查看所有状态
#   ./daemon-manager.sh restart           重启所有
#
# PID 文件: /mnt/e/ai_tools/mail/logs/daemon-<agent>.pid
# 日志文件: /mnt/e/ai_tools/mail/logs/daemon-<agent>.log

set -euo pipefail

MAIL_DIR="/mnt/e/ai_tools/mail"
DAEMON="$MAIL_DIR/mailbox-daemon.py"
CONFIG="$MAIL_DIR/store/config.json"
PID_DIR="$MAIL_DIR/logs"
DATA_DIR="$MAIL_DIR/store"

mkdir -p "$PID_DIR"

# 获取所有配置了 type 的 agent 列表
get_agents() {
    python3 -c "
import json
with open('$CONFIG') as f:
    cfg = json.load(f)
agents = []
for name, info in cfg.get('agents', {}).items():
    t = info.get('type', 'none')
    if t and t != 'none':
        agents.append(name)
print(' '.join(agents))
"
}

# 获取单个 agent 的 pid 文件路径
pid_file() { echo "$PID_DIR/daemon-$1.pid"; }

# 检查 agent 的 daemon 是否在运行
is_running() {
    local pid_file=$(pid_file "$1")
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        # 僵死, 清理 pid 文件
        rm -f "$pid_file"
    fi
    return 1
}

# 启动一个 agent 的 daemon
start_one() {
    local agent=$1
    if is_running "$agent"; then
        echo "  ✓ $agent 已在运行 (PID $(cat "$(pid_file "$agent")"))"
        return 0
    fi
    nohup python3 "$DAEMON" --agent "$agent" --data-dir "$DATA_DIR" \
        > "$PID_DIR/daemon-$agent-startup.log" 2>&1 &
    local pid=$!
    echo "$pid" > "$(pid_file "$agent")"
    echo "  🚀 $agent 已启动 (PID $pid)"
}

# 停止一个 agent 的 daemon
stop_one() {
    local agent=$1
    local pf=$(pid_file "$agent")
    if [ ! -f "$pf" ]; then
        echo "  - $agent 未运行"
        return 0
    fi
    local pid=$(cat "$pf")
    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null
        # 等待最多 5 秒
        for i in $(seq 1 5); do
            if ! kill -0 "$pid" 2>/dev/null; then break; fi
            sleep 1
        done
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        echo "  🛑 $agent 已停止 (PID $pid)"
    else
        echo "  - $agent 已不在运行"
    fi
    rm -f "$pf"
}

# 查看一个 agent 的状态
status_one() {
    local agent=$1
    local pf=$(pid_file "$agent")
    if [ -f "$pf" ] && kill -0 "$(cat "$pf")" 2>/dev/null; then
        local pid=$(cat "$pf")
        local uptime=$(ps -o etime -p "$pid" --no-headers 2>/dev/null || echo "?")
        echo "  🟢 $agent — PID $pid, 已运行 $uptime"
    else
        echo "  🔴 $agent — 已停止"
    fi
}

# ── 命令分发 ──

cmd="${1:-}"
shift 2>/dev/null || true

case "$cmd" in
    start)
        if [ -n "${1:-}" ]; then
            echo "📬 启动 daemon: $1"
            start_one "$1"
        else
            echo "📬 启动所有 daemon..."
            for agent in $(get_agents); do
                start_one "$agent"
            done
        fi
        ;;
    stop)
        if [ -n "${1:-}" ]; then
            echo "🛑 停止 daemon: $1"
            stop_one "$1"
        else
            echo "🛑 停止所有 daemon..."
            for agent in $(get_agents); do
                stop_one "$agent"
            done
        fi
        ;;
    status)
        echo "📋 Daemon 状态:"
        for agent in $(get_agents); do
            status_one "$agent"
        done
        echo ""
        echo "  配置了 type 的 agent: $(get_agents)"
        ;;
    restart)
        if [ -n "${1:-}" ]; then
            echo "🔄 重启 daemon: $1"
            stop_one "$1"
            sleep 1
            start_one "$1"
        else
            echo "🔄 重启所有 daemon..."
            for agent in $(get_agents); do
                stop_one "$agent"
            done
            sleep 1
            for agent in $(get_agents); do
                start_one "$agent"
            done
        fi
        ;;
    install-cron)
        echo "📦 安装 daemon 自守护 crontab..."
        SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
        CRON_JOB="* * * * * cd ${SCRIPT_DIR} && bash daemon-manager.sh watchdog > /dev/null 2>&1"
        (crontab -l 2>/dev/null | grep -v "daemon-manager.sh" ; echo "$CRON_JOB") | crontab -
        echo "  ✅ crontab 已安装: 每分钟检查 daemon 存活"
        ;;
    watchdog)
        # 供 crontab 每分钟调用：检测所有 daemon，挂了自动重启
        for agent in $(get_agents); do
            if ! is_running "$agent"; then
                echo "[$(date)] 🔴 $agent daemon 已停止, 自动重启..." >&2
                start_one "$agent"
            fi
        done
        ;;
    *)
        echo "用法: $0 {start|stop|status|restart|install-cron} [agent]"
        echo ""
        echo "  agent 可选, 不指定则操作所有"
        echo ""
        echo "  可用 agent: $(get_agents)"
        exit 1
        ;;
esac
