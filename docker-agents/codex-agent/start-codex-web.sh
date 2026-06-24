#!/bin/bash
# 在容器内启动 ttyd → tmux → codex，供 Windows 浏览器访问
set -euo pipefail

CODEX_HOME="${CODEX_HOME:-/home/node/.codex}"
WEB_PORT="${CODEX_WEB_PORT:-7682}"
AGENT="${CODEX_AGENT:-codex}"
MODEL="${CODEX_MODEL:-deepseek-v4-flash}"
CWD="${CODEX_WEB_CWD:-/mailbus/store}"
TMUX_SESSION="codex-${AGENT}"

if ! command -v ttyd >/dev/null 2>&1; then
  echo "[codex-web] ttyd not installed" >&2
  exit 1
fi

render-codex-config.sh

# 已有实例则跳过
if curl -sf "http://127.0.0.1:${WEB_PORT}/" >/dev/null 2>&1; then
  echo "[codex-web] already listening on :${WEB_PORT} agent=${AGENT}" >&2
  exit 0
fi

mkdir -p /tmp/codex-web
START_SCRIPT="/tmp/codex-web/start-${AGENT}.sh"
cat > "$START_SCRIPT" <<SCRIPT
#!/bin/bash
set +e
export CODEX_HOME="${CODEX_HOME}"
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
cd "${CWD}" || exit 1
exec codex -m "${MODEL}" --cd "${CWD}"
SCRIPT
chmod +x "$START_SCRIPT"

# tmux 保活：浏览器刷新后 session 仍在
if ! tmux has-session -t "${TMUX_SESSION}" 2>/dev/null; then
  tmux new-session -d -s "${TMUX_SESSION}" "$START_SCRIPT"
fi

nohup ttyd -p "${WEB_PORT}" -i 0.0.0.0 -W -t disableReuse=true \
  tmux attach -t "${TMUX_SESSION}" \
  >/tmp/codex-web/ttyd-${AGENT}.log 2>&1 &

for _ in $(seq 1 20); do
  if curl -sf "http://127.0.0.1:${WEB_PORT}/" >/dev/null 2>&1; then
    echo "[codex-web] ready http://0.0.0.0:${WEB_PORT} agent=${AGENT} session=${TMUX_SESSION}" >&2
    exit 0
  fi
  sleep 1
done

echo "[codex-web] failed to start on :${WEB_PORT}" >&2
exit 1
