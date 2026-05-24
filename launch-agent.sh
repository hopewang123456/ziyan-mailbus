#!/bin/bash
# 从 mailbus Web 看板启动指定 agent 的 CLI/浏览器窗口
# 所有启动配置读取自 config.json launch 字段，不再硬编码
# Usage: ./launch-agent.sh <agent_key> [browser|cli]

set -euo pipefail

AGENT_KEY="${1:-}"
LAUNCH_MODE="${2:-browser}"
CONFIG_FILE="/mnt/e/ai_tools/mail/store/config.json"

if [ -z "$AGENT_KEY" ]; then
  echo "Usage: launch-agent.sh <agent_key> [browser|cli]" >&2
  exit 1
fi

# ── 工具函数 ──

PS_HELPER="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"

start_wsl() {
  local cmd="$1"
  local ts=$(date +%s)
  local script="/tmp/launch-window-${ts}.sh"
  cat > "$script" <<- HEREDOC
#!/bin/bash
${cmd}
HEREDOC
  chmod +x "$script"
  $PS_HELPER -Command "Start-Process wsl.exe -ArgumentList '-d','Ubuntu','-e','bash','${script}'" 2>/dev/null || true
  (sleep 15 && rm -f "$script") &
}

start_browser() {
  local url="$1"
  $PS_HELPER -Command "Start-Process '$url'" 2>/dev/null || true
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
  start_browser "http://localhost:18789"
  echo "Launched $AGENT_KEY ($LAUNCH_MODE) [fallback]"
  exit 0
fi

KIND=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('kind','none'))")

if [ "$LAUNCH_MODE" = "browser" ]; then
  case "$KIND" in
    "openclaw_gateway")
      PORT=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('gateway_port',18789))")
      URL=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('url','http://localhost:{port}'))")
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

    *)
      start_browser "http://localhost:18789"
      ;;
  esac

else
  # ── CLI 模式 ──
  case "$KIND" in
    "shell")
      CMD=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('command',''))")
      if [ -n "$CMD" ]; then
        # 替换模板变量
        SESSION=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session','main'))")
        HERMES_HOME=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('hermes_home','/mnt/e/hermes-data/.hermes'))")
        PROFILE_ARGS=$(echo "$CFG" | python3 -c "import json,sys; print(json.load(sys.stdin).get('profile_args',''))")
        CMD=$(subst_vars "$CMD" "session" "$SESSION" "hermes_home" "$HERMES_HOME" "profile_args" "$PROFILE_ARGS" "agent" "$AGENT_KEY")
        start_wsl "$CMD"
      else
        start_browser "http://localhost:18789"
      fi
      ;;

    "none")
      start_browser "http://localhost:18789"
      ;;

    *)
      start_browser "http://localhost:18789"
      ;;
  esac
fi

echo "Launched $AGENT_KEY ($LAUNCH_MODE)"
