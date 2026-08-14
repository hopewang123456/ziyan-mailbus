#!/bin/bash
# Mailbus - OpenClaw container entrypoint
set -euo pipefail

export OPENCLAW_STATE_DIR=/workspace/data/.openclaw
export OPENCLAW_CONFIG_PATH="$OPENCLAW_STATE_DIR/openclaw.json"

# 从 Hermes 挂载目录注入 API Key
# shellcheck disable=SC1091
source /load-hermes-env.sh

sleep 3
cd /workspace

bash /init-openclaw-profiles.sh || {
  echo "[entrypoint] WARN: init-openclaw-profiles failed — seeding minimal openclaw.json"
  mkdir -p /workspace/data/.openclaw
  if [ ! -f /workspace/data/.openclaw/openclaw.json ]; then
    printf '%s\n' '{"agents":{"list":[]},"gateway":{"bind":"auto"}}' > /workspace/data/.openclaw/openclaw.json
  fi
  bash /init-openclaw-profiles.sh || echo "[entrypoint] WARN: profile init still failed — gateways may be degraded"
}

if [ -f /mailbus/tools/sync-all-agent-layers.py ]; then
  python3 /mailbus/tools/sync-all-agent-layers.py --data-dir /mailbus/store --skip-hermes --skip-codex --skip-claude || true
fi

echo "[entrypoint] Starting OpenClaw gateways..."
OPENCLAW_TOKEN="${OPENCLAW_GATEWAY_TOKEN:-change-me}"

gateway_env_base=(
  "DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY:-}"
  "OPENAI_API_KEY=${OPENAI_API_KEY:-}"
  "GLM_API_KEY=${GLM_API_KEY:-}"
  "ZHIPU_API_KEY=${ZHIPU_API_KEY:-}"
  "DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY:-}"
  "QWEN_API_KEY=${QWEN_API_KEY:-}"
  "ALIBABA_API_KEY=${ALIBABA_API_KEY:-}"
  "HTTP_PROXY=${HTTP_PROXY:-}"
  "HTTPS_PROXY=${HTTPS_PROXY:-}"
  "NO_PROXY=${NO_PROXY:-localhost,127.0.0.1,::1,iii-engine,agentmemory,mailbus,172.28.0.0/16,host.docker.internal}"
)

start_gateway() {
  local name="$1"
  local port="$2"
  local statedir="/workspace/data/.openclaw-${name}"
  local extra=()
  if [ "${OPENCLAW_ALLOW_OLDER_DESTRUCTIVE:-0}" = "1" ]; then
    extra=("OPENCLAW_ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS=1")
  fi
  # 默认保留 pairing；仅 RESET_OPENCLAW_PAIRING=1 时清理（避免普通重启丢配对）
  if [ "${RESET_OPENCLAW_PAIRING:-0}" = "1" ]; then
    rm -rf "${statedir}/devices" "${statedir}/identity" 2>/dev/null || true
  fi
  # 清理可能卡住的迁移锁（升级版本后常见）
  find "$statedir" -maxdepth 3 \( -name "*.lock" -o -name "*.migrating" -o -name "migration.lock" \) -delete 2>/dev/null || true
  # 2026.7+：缺 deepseek plugin 会弹出交互警告并卡住 gateway
  env OPENCLAW_STATE_DIR="$statedir" OPENCLAW_CONFIG_PATH="${statedir}/openclaw.json" \
    openclaw --no-color plugins install @openclaw/deepseek-provider \
    >/tmp/openclaw-plugin-${name}.log 2>&1 || true
  nohup env \
    "${extra[@]}" \
    OPENCLAW_STATE_DIR="$statedir" \
    OPENCLAW_CONFIG_PATH="${statedir}/openclaw.json" \
    CI=1 NO_COLOR=1 \
    "${gateway_env_base[@]}" \
    openclaw --no-color gateway run --allow-unconfigured --auth token --token "$OPENCLAW_TOKEN" \
      --port "$port" --bind lan --force \
    >"/tmp/openclaw-gw-${port}.log" 2>&1 &
  echo "  ${name} (${port}) started [state=${statedir}] pid=$!"
}

# 从 store/config.json 读取 openclaw agents（名→端口）；缺失时回落 demo 名单
while read -r name port; do
  start_gateway "$name" "$port"
  # 错开启动，避免多 profile 同时抢迁移锁
  sleep 4
done < <(python3 -c "
import json, os
try:
    cfg = json.load(open('/mailbus/store/config.json', encoding='utf-8'))
except Exception:
    print('agent-m 18789')
    print('agent-l 18790')
    raise SystemExit
for a, c in cfg.get('agents', {}).items():
    if (c.get('type') or '') != 'openclaw':
        continue
    port = 18789
    browser = (c.get('launch') or {}).get('browser') or {}
    port = browser.get('gateway_port') or (c.get('docker') or {}).get('port') or port
    print(f'{a} {port}')
")

# 等待端口就绪（最多 ~90s）
for port in 18789 18790; do
  ok=0
  for _ in $(seq 1 30); do
    if python3 -c "import socket;s=socket.socket();s.settimeout(1);r=s.connect_ex(('127.0.0.1',$port));s.close();raise SystemExit(0 if r==0 else 1)" 2>/dev/null; then
      ok=1
      break
    fi
    sleep 3
  done
  echo "  port ${port}: $([ "$ok" = 1 ] && echo ready || echo NOT-ready — see /tmp/openclaw-gw-${port}.log)"
done

echo "[entrypoint] All OpenClaw gateways launched"
tail -f /dev/null
