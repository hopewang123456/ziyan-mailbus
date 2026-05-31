#!/bin/bash
# ============================================================
# mailbus-boot.sh v3.0 — 智能检测 + 动态启动
#
# 用法:
#   ./mailbus-boot.sh             启动已装 CLI 对应的服务
#   ./mailbus-boot.sh --status    查看各进程运行状态
#   ./mailbus-boot.sh --stop      停止所有 mailbus 相关进程
#   ./mailbus-boot.sh --restart   重启全部
#
# 原理：读 config.json 检测各 CLI 是否安装，只启已装的服务
# ============================================================

STORE_DIR="/mnt/e/ai_tools/mail/store"
MAIL_DIR="/mnt/e/ai_tools/mail"
CONFIG_PATH="$STORE_DIR/config.json"

# ── CLI 检测 ──────────────────────────────────────────────────

_has_hermes() {
    test -f /mnt/e/hermes-data/.hermes/hermes-agent/venv/bin/hermes
}

_has_openclaw() {
    command -v openclaw &>/dev/null || test -f /home/administrator/.npm-global/bin/openclaw
}

_has_cline() {
    command -v cline &>/dev/null || test -f /home/administrator/.npm-global/bin/cline
}

_has_opencode() {
    command -v opencode &>/dev/null || test -f /mnt/e/ai_tools/opencode/opencode
}

# ── 从 config.json 检测可启动的 agent ──────────────────────────

_detect_agents() {
    if [ ! -f "$CONFIG_PATH" ]; then
        echo "[]"
        return
    fi

    # Python 脚本内部自检 CLI，不需 shell 传变量
    python3 << 'PYDETECT'
import json, sys, os

config_path = "/mnt/e/ai_tools/mail/store/config.json"
with open(config_path) as f:
    config = json.load(f)

agents = config.get('agents', {})

# 直接检测 CLI 是否可用
cli_ok = {
    'hermes': os.path.isfile('/mnt/e/hermes-data/.hermes/hermes-agent/venv/bin/hermes'),
    'hermes_profile': os.path.isfile('/mnt/e/hermes-data/.hermes/hermes-agent/venv/bin/hermes'),
    'openclaw': any((
        os.path.isfile('/home/administrator/.npm-global/bin/openclaw'),
        bool(os.system('command -v openclaw >/dev/null 2>&1') == 0),
    )),
    'cline': os.path.isfile('/home/administrator/.npm-global/bin/cline'),
    'opencode': os.path.isfile('/mnt/e/ai_tools/opencode/opencode'),
}

results = []
for name, cfg in agents.items():
    agent_type = cfg.get('type', '')
    launch = cfg.get('launch', {})
    template_name = launch.get('template', '')
    browser = launch.get('browser', {})
    start_cmd = browser.get('start_command', '')

    if template_name in ('openclaw_gateway', 'hermes_dashboard'):
        if not cli_ok.get(agent_type, False):
            continue
        port = browser.get('gateway_port') or browser.get('dashboard_port') or browser.get('port', '')
        display_name = cfg.get('name', name)
        icon = '🦞' if agent_type == 'openclaw' else '🪷' if 'hermes' in agent_type else '?'
        results.append({
            'name': name,
            'display': display_name,
            'type': agent_type,
            'template': template_name,
            'port': str(port) if port else '',
            'start_cmd': start_cmd,
            'icon': icon,
        })

print(json.dumps(results, ensure_ascii=False))
PYDETECT
}

# ── 全局进程列表（动态构建）────────────────────────────────────

PROC_NAMES=()
declare -A PROCS

_build_proc_list() {
    PROC_NAMES=()
    PROCS=()

    # bus.py 总是存在
    PROC_NAMES+=("bus.py (mailbus API)")
    PROCS["bus.py (mailbus API)"]="python3.*bus.py serve"

    # 从 config.json 读取可启动的 agent
    local agents_json
    agents_json=$(_detect_agents)

    if [ "$agents_json" != "[]" ] && [ -n "$agents_json" ]; then
        while IFS= read -r line; do
            [ -z "$line" ] && continue
            local name display port icon
            name=$(echo "$line" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['name'])" 2>/dev/null) || continue
            display=$(echo "$line" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['display'])" 2>/dev/null) || continue
            port=$(echo "$line" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['port'])" 2>/dev/null) || continue
            icon=$(echo "$line" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['icon'])" 2>/dev/null) || continue
            local label="$icon $display ($name:$port)"
            PROC_NAMES+=("$label")
            PROCS["$label"]="port:$port"
        done < <(echo "$agents_json" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for item in data:
    print(json.dumps(item))
")
    fi
}

# ── 进程检测辅助 ──────────────────────────────────────────────

_check_process() {
    local name="$1"
    local val="${PROCS[$name]}"

    # 端口检测
    if [[ "$val" == port:* ]]; then
        local port="${val#port:}"
        if [ -n "$port" ]; then
            ss -tlnp 2>/dev/null | grep -q ":$port " && return 0 || return 1
        fi
    fi

    # pgrep 检测
    if pgrep -f "$val" > /dev/null 2>&1; then
        return 0
    fi
    return 1
}

_get_pids() {
    local name="$1"
    local val="${PROCS[$name]}"

    if [[ "$val" == port:* ]]; then
        local port="${val#port:}"
        ss -tlnp 2>/dev/null | grep ":$port " | awk '{print $NF}' | tr ',' ' '
        return
    fi
    pgrep -f "$val" | tr '\n' ' '
}

# ── 启动函数 ──────────────────────────────────────────────────

launch_all() {
    _build_proc_list

    echo ""
    echo "╔══════════════════════════════════════════╗"
    echo "║   📬 mailbus 智能启动 v3.0               ║"
    echo "╚══════════════════════════════════════════╝"
    echo ""

    local total=${#PROC_NAMES[@]}
    local idx=1

    # ── 1. bus.py ──
    echo "[$idx/$total] mailbus API (:9812)..."
    if _check_process "bus.py (mailbus API)"; then
        echo "  ⚠️  已在运行"
    else
        cd "$MAIL_DIR"
        nohup python3 bus.py serve --host 0.0.0.0 --port 9812 --data-dir "$STORE_DIR" \
            >> "$STORE_DIR/cron.log" 2>&1 &
        echo "  ✅ PID: $!"
        ((launched++))
    fi
    ((idx++))

    # ── 2..n. config.json 中的 agent ──
    local agents_json
    agents_json=$(_detect_agents)

    if [ "$agents_json" != "[]" ] && [ -n "$agents_json" ]; then
        echo "$agents_json" | python3 -c "
import sys, json, subprocess, os

data = json.load(sys.stdin)
for item in data:
    name = item['name']
    display = item['display']
    port = item['port']
    start_cmd = item['start_cmd']
    icon = item['icon']
    agent_type = item['type']

    idx = ${idx}
    total = ${total}

    print(f'[{idx}/$total] {icon} {display} (:{port})...')

    # 检查端口是否已占用
    result = subprocess.run(['ss', '-tlnp'], capture_output=True, text=True, timeout=5)
    if f':{port} ' in result.stdout:
        print(f'  ⚠️  :{port} 已被占用，跳过')
        idx += 1
        continue

    # 执行启动命令
    log_file = f'/tmp/mailbus-{name}-launch.log'
    print(f'  🚀 {start_cmd[:80]}...')

    try:
        proc = subprocess.Popen(
            ['nohup', 'sh', '-c', start_cmd],
            stdout=open(log_file, 'w'),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        print(f'  ✅ PID: {proc.pid}')
    except Exception as e:
        print(f'  ❌ 启动失败: {e}')

    idx += 1
" 2>&1
    else
        echo "  没有可启动的 agent（未检测到对应的 CLI 工具）"
    fi

    echo ""
    echo "╔══════════════════════════════════════════╗"
    echo "║   ✅ 启动完成！                          ║"
    echo "╚══════════════════════════════════════════╝"
    echo ""
    echo "💡 查看状态:  ./mailbus-boot.sh --status"
    echo "💡 停止全部:  ./mailbus-boot.sh --stop"
    echo ""

    # 展示已检测到的 CLI
    echo "📦 已检测到以下 CLI 工具:"
    _has_hermes    && echo "  ✅ Hermes   — hermes-agent (venv)" || echo "  ❌ Hermes   — 未安装"
    _has_openclaw  && echo "  ✅ OpenClaw — 可用" || echo "  ❌ OpenClaw — 未安装"
    _has_cline     && echo "  ✅ Cline    — 可用" || echo "  ❌ Cline    — 未安装"
    _has_opencode  && echo "  ✅ OpenCode — 可用" || echo "  ❌ OpenCode — 未安装"
    echo ""
}

# ── 状态查看 ──────────────────────────────────────────────────

show_status() {
    _build_proc_list

    echo ""
    echo "📊 mailbus 进程状态"
    echo "──────────────────────────────"
    for name in "${PROC_NAMES[@]}"; do
        if _check_process "$name"; then
            pids=$(_get_pids "$name")
            echo "  ✅ $name — $pids"
        else
            echo "  ❌ $name — 未运行"
        fi
    done
    echo ""

    echo "📡 端口监听状态:"
    local ports=()
    ports+=(9812)
    # 从 config.json 收集所有 agent 端口
    local agents_json
    agents_json=$(_detect_agents)
    if [ "$agents_json" != "[]" ] && [ -n "$agents_json" ]; then
        while IFS= read -r port; do
            [ -n "$port" ] && ports+=("$port")
        done < <(echo "$agents_json" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for item in data:
    if item.get('port'):
        print(item['port'])
")
    fi

    for port in "${ports[@]}"; do
        if ss -tlnp 2>/dev/null | grep -q ":$port "; then
            pid_info=$(ss -tlnp 2>/dev/null | grep ":$port " | awk '{print $NF}')
            echo "  ✅ :$port — $pid_info"
        else
            echo "  ❌ :$port — 未监听"
        fi
    done
    echo ""

    # 📦 Inbox 积压
    echo "📦 Inbox 积压:"
    if [ -f "$CONFIG_PATH" ]; then
        python3 -c "
import json, os
with open('$CONFIG_PATH') as f:
    cfg = json.load(f)
for name, info in cfg.get('agents', {}).items():
    inbox_path = info.get('inbox', f'$STORE_DIR/inbox/{name}/inbox.json')
    if os.path.exists(inbox_path):
        size = os.path.getsize(inbox_path)
        try:
            with open(inbox_path) as f2:
                d = json.load(f2)
            count = len(d.get('messages', []))
            unread = ' 📩' if d.get('has_unread') else ''
            print(f'  {info.get(\"name\",name)}: {count} 条 / {size//1024}K{unread}')
        except:
            print(f'  {info.get(\"name\",name)}: {size//1024}K')
" 2>/dev/null || echo "  (读取失败)"
    fi
    echo ""

    # CLI 工具状态
    echo "🔧 已安装 CLI:"
    _has_hermes    && echo "  ✅ Hermes"   || echo "  ❌ Hermes"
    _has_openclaw  && echo "  ✅ OpenClaw" || echo "  ❌ OpenClaw"
    _has_cline     && echo "  ✅ Cline"    || echo "  ❌ Cline"
    _has_opencode  && echo "  ✅ OpenCode" || echo "  ❌ OpenCode"
    echo ""
}

# ── 停止 ──────────────────────────────────────────────────────

stop_all() {
    _build_proc_list

    echo ""
    echo "🛑 停止所有 mailbus 相关进程..."
    echo "──────────────────────────────"
    for name in "${PROC_NAMES[@]}"; do
        if _check_process "$name"; then
            local val="${PROCS[$name]}"
            if [[ "$val" == port:* ]]; then
                local port="${val#port:}"
                pkill -f "port $port" 2>/dev/null || true
                # openclaw 特殊处理（command line 不显示参数）
                if [ "$port" = "18789" ] || [ "$port" = "18790" ]; then
                    pkill -f "openclaw" 2>/dev/null || true
                fi
            else
                pkill -f "$val" 2>/dev/null || true
            fi
            echo "  ✅ 已停止: $name"
        else
            echo "  ⚠️  未运行: $name"
        fi
    done
    echo ""
    echo "✅ 全部停止完成"
    echo "💡 重新启动: ./mailbus-boot.sh"
}

# ── 参数解析 ──────────────────────────────────────────────────

case "${1:-}" in
    --status|-s)
        show_status
        ;;
    --stop|-S)
        stop_all
        ;;
    --restart|-r)
        stop_all
        sleep 2
        launch_all
        ;;
    --help|-h)
        echo "用法: $0 [--status|--stop|--restart|--help]"
        echo ""
        echo "  不带参数    智能检测 CLI 并启动对应的服务"
        echo "  --status    查看各进程运行状态"
        echo "  --stop      停止所有 mailbus 相关进程"
        echo "  --restart   重启全部"
        echo "  --help      显示此帮助"
        ;;
    "")
        launch_all
        ;;
    *)
        echo "未知参数: $1"
        echo "用法: $0 [--status|--stop|--restart|--help]"
        exit 1
        ;;
esac
