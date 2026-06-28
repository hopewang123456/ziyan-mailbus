#!/bin/bash
# 从 mailbus Web 看板启动指定 agent 的 CLI/浏览器窗口
# 所有启动配置读取自 config.json launch 字段，不再硬编码
# Usage: ./launch-agent.sh <agent_key> [browser|cli|desktop]

set -euo pipefail

AGENT_KEY="${1:-}"
LAUNCH_MODE="${2:-browser}"
# 检测容器环境，自适应 config 路径
if [ -f "/mailbus/store/config.json" ]; then
  CONFIG_FILE="/mailbus/store/config.json"
else
  CONFIG_FILE="/mnt/e/ai_tools/mail/store/config.json"
fi

if [ -z "$AGENT_KEY" ]; then
  echo "Usage: launch-agent.sh <agent_key> [browser|cli|desktop]" >&2
  exit 1
fi

# ── 工具函数 ──

PS_HELPER="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"

start_wsl() {
  local cmd="$1"
  local name="${2:-${AGENT_KEY}}"
  # 容器内 / 有 docker.sock：优先 watchdog queue；写失败则回退直接弹窗
  if [ -S /var/run/docker.sock ]; then
    local ts=$(date +%s)
    local queue_dir="/tmp/mailbus-launch-queue"
    mkdir -p "$queue_dir" 2>/dev/null || true
    chmod 1777 "$queue_dir" 2>/dev/null || true
    local launch_file="${queue_dir}/${name}-${ts}.launch"
    if printf '%s\n%s\n' "$cmd" "$name" > "$launch_file" 2>/dev/null; then
      chmod 666 "$launch_file" 2>/dev/null || true
      echo "Launched $name (cli) [docker-wsl bridge, file: $launch_file]"
      return 0
    fi
    echo "[launch-agent] queue 不可写，回退直接弹 WSL 窗口" >&2
  fi
  # 宿主机：弹新 WSL 窗口
  local ts=$(date +%s)
  local script="/tmp/launch-window-${ts}.sh"
  cat > "$script" <<- HEREDOC
#!/bin/bash
# === launch-agent.sh wrapper ===
# 防止子脚本的 set -e 导致窗口闪退
set +e
${cmd}
EXIT_CODE=\$?
echo ""
if [ \$EXIT_CODE -ne 0 ]; then
  echo "⚠️  脚本异常退出 (code: \$EXIT_CODE)"
else
  echo "✅ 脚本执行完毕 (code: \$EXIT_CODE)"
fi
echo "按 Enter 键关闭窗口..."
read
HEREDOC
  chmod +x "$script"
  $PS_HELPER -Command "Start-Process wsl.exe -ArgumentList '-d','Ubuntu','-e','bash','${script}'" 2>/dev/null || true
  # 延迟删除脚本（给用户留足操作时间，避免边用边删）
  (sleep 600 && rm -f "$script") &
}

start_browser() {
  local url="$1"
  local err=""
  # 方法1: cmd.exe /c start（最可靠，直接调用 Windows Shell 协议关联）
  local CMD_HELPER="/mnt/c/Windows/System32/cmd.exe"
  if [ -x "$CMD_HELPER" ]; then
    err=$("$CMD_HELPER" /c start "" "$url" 2>&1) && return 0
  fi
  # 方法2: PowerShell Start-Process（回退方案）
  if [ -x "$PS_HELPER" ]; then
    err=$("$PS_HELPER" -NoProfile -Command "Start-Process '$url'" 2>&1) && return 0
  fi
  # 都失败了，输出错误
  echo "[ERROR] 无法打开浏览器: $url" >&2
  echo "[ERROR] cmd.exe: ${err:-not found}" >&2
  return 1
}

ensure_codex_container() {
  local wait_sec="${1:-5}"
  CONTAINER=""
  if [ -f "/mailbus/lib/agent_adapters.py" ]; then
    MB_ROOT="/mailbus"
  else
    MB_ROOT="$(dirname "$0")"
  fi
  CONTAINER=$(python3 -c "
import json, sys
sys.path.insert(0, '${MB_ROOT}')
from lib.agent_adapters import resolve_container
with open('${CONFIG_FILE}') as f:
    cfg = json.load(f)
agent = cfg['agents']['${AGENT_KEY}']
service = (agent.get('docker') or {}).get('service') or '${AGENT_KEY}'
print(resolve_container(agent, '${AGENT_KEY}', service))
" 2>/dev/null || true)
  if [ -n "$CONTAINER" ] && command -v docker >/dev/null 2>&1; then
    if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$CONTAINER"; then
      docker start "$CONTAINER" 2>/dev/null || true
      sleep "$wait_sec"
    fi
  fi
}

launch_codex_interactive() {
  local wait_sec="${1:-5}"
  ensure_codex_container "$wait_sec"
  if [ -f "/mailbus/tools/resolve-agent-cli.py" ]; then
    RESOLVER="/mailbus/tools/resolve-agent-cli.py"
    DATA_DIR="/mailbus/store"
  else
    RESOLVER="$(dirname "$0")/tools/resolve-agent-cli.py"
    DATA_DIR="$(dirname "$CONFIG_FILE")"
  fi
  CMD=$(python3 "$RESOLVER" "$AGENT_KEY" --mode interactive --data-dir "$DATA_DIR" 2>/dev/null || true)
  if [ -n "$CMD" ]; then
    start_wsl "$CMD"
  else
    echo "[ERROR] 无法解析 Codex CLI 命令" >&2
    return 1
  fi
}

launch_claude_interactive() {
  if [ -f "/mailbus/tools/ops/tools/ops/launch-claude-cli.py" ]; then
    RESOLVER="/mailbus/tools/ops/tools/ops/launch-claude-cli.py"
    DATA_DIR="/mailbus/store"
  else
    RESOLVER="$(dirname "$0")/tools/tools/ops/launch-claude-cli.py"
    DATA_DIR="$(dirname "$CONFIG_FILE")"
  fi
  if python3 "$RESOLVER" "$AGENT_KEY" --data-dir "$DATA_DIR"; then
    echo "Launched $AGENT_KEY (cli)"
    return 0
  fi
  echo "[ERROR] Claude Code CLI 启动失败" >&2
  return 1
}

launch_codex_browser() {
  # Docker 内 codexapp 可视化 Web UI，Windows 浏览器直接访问
  local wait_sec url web_port ttyd_url ready
  wait_sec=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('start_wait_seconds',15))")
  url=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('url','http://127.0.0.1:9240'))")
  web_port=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('web_port',''))")
  ttyd_url=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('ttyd_url',''))")
  url=$(subst_vars "$url" "agent" "$AGENT_KEY" "port" "${web_port}")
  ttyd_url=$(subst_vars "$ttyd_url" "agent" "$AGENT_KEY" "port" "${web_port}")
  ensure_codex_container "$wait_sec"
  ready=0
  if curl -sf "$url" >/dev/null 2>&1; then
    ready=1
  elif [ -n "$CONTAINER" ] && command -v docker >/dev/null 2>&1; then
    docker exec "$CONTAINER" ensure-codex-browser.sh 2>/dev/null \
      || docker exec "$CONTAINER" start-codex-ui.sh 2>/dev/null \
      || true
    for i in $(seq 1 "$wait_sec"); do
      if curl -sf "$url" >/dev/null 2>&1; then ready=1; break; fi
      sleep 1
    done
    if [ "$ready" -eq 0 ]; then
      echo "[launch-agent] codexapp 未就绪，重试 ensure-codex-browser…" >&2
      docker exec "$CONTAINER" bash -lc 'rm -f /home/node/.codex/auth.json; ensure-codex-browser.sh' 2>/dev/null || true
      for i in $(seq 1 "$wait_sec"); do
        if curl -sf "$url" >/dev/null 2>&1; then ready=1; break; fi
        sleep 1
      done
    fi
  fi
  if [ "$ready" -eq 0 ]; then
    echo "[WARN] codexapp 仍未响应: $url" >&2
    if [ -n "$ttyd_url" ] && curl -sf "$ttyd_url" >/dev/null 2>&1; then
      echo "[launch-agent] 改用 ttyd 备用终端: $ttyd_url" >&2
      start_browser "$ttyd_url"
      echo "Launched $AGENT_KEY codex-ttyd $ttyd_url (codexapp unavailable)"
      return 0
    fi
    echo "[ERROR] codexapp 与 ttyd 均不可用" >&2
    return 1
  fi
  start_browser "$url"
  echo "Launched $AGENT_KEY codex-ui $url"
}

launch_claude_browser() {
  local wait_sec url web_port resolver data_dir
  wait_sec=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('start_wait_seconds',15))")
  url=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('url','http://127.0.0.1:{port}/'))")
  web_port=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('web_port','9260'))")
  url=$(subst_vars "$url" "agent" "$AGENT_KEY" "port" "${web_port}")

  if [ -f "/mailbus/tools/ops/tools/ops/launch-claude-browser.py" ]; then
    resolver="/mailbus/tools/ops/tools/ops/launch-claude-browser.py"
    data_dir="/mailbus/store"
  else
    resolver="$(dirname "$0")/tools/tools/ops/launch-claude-browser.py"
    data_dir="$(dirname "$CONFIG_FILE")"
  fi

  if python3 "$resolver" "$AGENT_KEY" --data-dir "$data_dir" --ensure-only --wait "$wait_sec"; then
    start_browser "$url"
    echo "Launched $AGENT_KEY claude-ttyd $url"
    return 0
  fi

  echo "[ERROR] Claude ttyd 启动失败" >&2
  return 1
}

launch_agent_desktop() {
  local resolver data_dir
  if [ -f "/mailbus/tools/ops/tools/ops/launch-agent-desktop.py" ]; then
    resolver="/mailbus/tools/ops/tools/ops/launch-agent-desktop.py"
    data_dir="/mailbus/store"
  else
    resolver="$(dirname "$0")/tools/tools/ops/launch-agent-desktop.py"
    data_dir="$(dirname "$CONFIG_FILE")"
  fi
  python3 "$resolver" "$AGENT_KEY" --data-dir "$data_dir"
}

# ── JSON 读取函数 ──
# 返回合并后的配置 JSON（模板+agent覆盖）

read_merged_cfg() {
  python3 -c "
import json, sys
with open('$CONFIG_FILE') as f:
    cfg = json.load(f)
agent = cfg['agents'].get('$AGENT_KEY')
if not agent:
    sys.exit(1)
tmpl_name = agent.get('launch', {}).get('template', '')
tmpl = cfg.get('agent_types', {}).get('launch_templates', {}).get(tmpl_name, {})
launch = agent.get('launch', {})
mode = '$LAUNCH_MODE'
# 合并模板和 agent 配置（agent 覆盖模板）
if mode == 'browser':
    result = dict(tmpl.get('browser', {}))
    result.update(launch.get('browser', {}))
elif mode == 'desktop':
    result = dict(tmpl.get('desktop', {}))
    result.update(launch.get('desktop', {}))
else:
    result = dict(tmpl.get('cli', {}))
    result.update(launch.get('cli', {}))
result['kind'] = result.get('kind', 'none')
# 添加 agent 模板名称用于参考
result['_template'] = tmpl_name
print(json.dumps(result, ensure_ascii=False))
" 2>/dev/null
}

# ── 模板变量替换 ──
# 将 {port} {agent} {hermes_home} {session} {profile_args} {url} 替换为实际值

subst_vars() {
  local str="$1"
  shift
  while [ $# -ge 2 ]; do
    local key="$1"
    local val="$2"
    shift 2
    str="${str//\{${key}\}/${val}}"
  done
  echo "$str"
}

# ── 获取配置并执行 ──

CFG=$(read_merged_cfg)
if [ -z "$CFG" ]; then
  echo "[ERROR] 无法读取 $AGENT_KEY 的 launch 配置 ($CONFIG_FILE)" >&2
  exit 1
fi

KIND=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('kind','none'))")

if [ "$LAUNCH_MODE" = "desktop" ]; then
  ENABLED=$(echo "$CFG" | python3 -c "import json,sys; d=json.load(sys.stdin); print('false' if d.get('enabled') is False else ('true' if d.get('kind') else 'false'))")
  if [ "$ENABLED" != "true" ]; then
    echo "[ERROR] agent $AGENT_KEY 未配置 launch.desktop（enabled + kind）" >&2
    exit 1
  fi
  launch_agent_desktop
elif [ "$LAUNCH_MODE" = "browser" ]; then
  case "$KIND" in
    "openclaw_gateway")
      PORT=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('gateway_port',18789))")
      URL="http://localhost:${PORT}/chat"
      TOKEN="${OPENCLAW_GATEWAY_TOKEN:-ziyan-team}"
      URL="${URL}?token=${TOKEN}"
      URL=$(subst_vars "$URL" "port" "$PORT" "agent" "$AGENT_KEY")
      START_CMD=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('start_command',''))")
      WAIT_SEC=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('start_wait_seconds',20))")

      if ! curl -s -o /dev/null "http://localhost:${PORT}" 2>/dev/null; then
        if [ -n "$START_CMD" ]; then
          CMD=$(subst_vars "$START_CMD" "port" "$PORT" "agent" "$AGENT_KEY")
          eval "$CMD"
          for i in $(seq 1 "$WAIT_SEC"); do
            sleep 1
            if curl -s -o /dev/null "http://localhost:${PORT}" 2>/dev/null; then break; fi
          done
        fi
      fi
      start_browser "$URL"
      ;;

    "hermes_dashboard")
      PORT=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('dashboard_port',9119))")
      URL=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('url','http://localhost:{port}/chat'))")
      HERMES_HOME=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('hermes_home','/mnt/e/hermes-data/.hermes'))")
      START_CMD=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('start_command',''))")
      WAIT_SEC=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('start_wait_seconds',15))")

      URL=$(subst_vars "$URL" "port" "$PORT" "agent" "$AGENT_KEY")

      if ! curl -s -o /dev/null "http://localhost:${PORT}" 2>/dev/null; then
        if [ -n "$START_CMD" ]; then
          CMD=$(subst_vars "$START_CMD" "port" "$PORT" "hermes_home" "$HERMES_HOME" "agent" "$AGENT_KEY")
          # 预先加载 openai 避免多线程 race condition
          PRELOAD="python3 -c \"import openai\" 2>/dev/null &&"
          eval "$PRELOAD $CMD"
          for i in $(seq 1 "$WAIT_SEC"); do
            sleep 1
            if curl -s -o /dev/null "http://localhost:${PORT}" 2>/dev/null; then break; fi
          done
        fi
      fi
      start_browser "$URL"
      ;;

    "url_only")
      URL=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('url','http://localhost:18789'))")
      URL=$(subst_vars "$URL" "agent" "$AGENT_KEY")
      start_browser "$URL"
      ;;

    "codex_desktop"|"codex_web"|"codex_ui"|"codex_docker")
      launch_codex_browser
      ;;

    "claude_ttyd"|"claude_web")
      launch_claude_browser
      ;;

    *)
      echo "[ERROR] 未知 browser kind '$KIND' for agent $AGENT_KEY" >&2
      exit 1
      ;;
  esac

else
  # ── CLI 模式 ──
  case "$KIND" in
    "shell")
      TEMPLATE=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('_template',''))")
      if [ "$TEMPLATE" = "codex_docker" ]; then
        WAIT_SEC=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('start_wait_seconds',5))")
        launch_codex_interactive "$WAIT_SEC"
      elif [ "$TEMPLATE" = "claude_host" ]; then
        launch_claude_interactive
      else
        if [ -f "/mailbus/tools/resolve-agent-cli.py" ]; then
          RESOLVER="/mailbus/tools/resolve-agent-cli.py"
          DATA_DIR="/mailbus/store"
        else
          RESOLVER="$(dirname "$0")/tools/resolve-agent-cli.py"
          DATA_DIR="$(dirname "$CONFIG_FILE")"
        fi
        CMD=$(python3 "$RESOLVER" "$AGENT_KEY" --mode interactive --data-dir "$DATA_DIR" 2>/dev/null || true)
        if [ -z "$CMD" ]; then
          CMD=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('command',''))")
        fi
        if [ -n "$CMD" ]; then
          SESSION=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session','main'))")
          HERMES_HOME=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('hermes_home','/mnt/e/hermes-data/.hermes'))")
          PROFILE_ARGS=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('profile_args',''))")
          CMD=$(subst_vars "$CMD" "session" "$SESSION" "hermes_home" "$HERMES_HOME" "profile_args" "$PROFILE_ARGS" "agent" "$AGENT_KEY")
          start_wsl "$CMD"
        else
          echo "[ERROR] 无法解析 $AGENT_KEY 的 CLI 命令" >&2
          exit 1
        fi
      fi
      ;;

    "none")
      echo "[ERROR] agent $AGENT_KEY 未配置 CLI" >&2
      exit 1
      ;;

    *)
      echo "[ERROR] 未知 CLI kind '$KIND' for agent $AGENT_KEY" >&2
      exit 1
      ;;
  esac
fi

echo "Launched $AGENT_KEY ($LAUNCH_MODE)"
