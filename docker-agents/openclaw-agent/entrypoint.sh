#!/bin/bash
# ziyan AI Team - OpenClaw container entrypoint
set -euo pipefail

export OPENCLAW_STATE_DIR=/workspace/data/.openclaw
export OPENCLAW_CONFIG_PATH="$OPENCLAW_STATE_DIR/openclaw.json"

# 配置里使用 WSL 路径，容器内做兼容
mkdir -p /mnt/e/ai_tools
ln -sfn /workspace /mnt/e/ai_tools/openclaw_space

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

if [ -x /mailbus/tools/sync-openclaw-framework-skill.sh ]; then
  for agent in xiaoqi yige; do
    OPENCLAW_AGENT="$agent" OPENCLAW_SKILLS_DIR="/workspace/skills" \
      bash /mailbus/tools/sync-openclaw-framework-skill.sh || true
  done
fi

echo "[entrypoint] Starting OpenClaw gateways..."
OPENCLAW_TOKEN="${OPENCLAW_GATEWAY_TOKEN:-ziyan-team}"

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
  if [ "$name" = "yige" ]; then
    extra=("OPENCLAW_ALLOW_OLDER_BINARY_DESTRUCTIVE_ACTIONS=1")
  fi
  # 容器重建后浏览器 localStorage 里的 device token 常与服务端不一致 → 清空后强制重新配对
  rm -rf "${statedir}/devices" "${statedir}/identity" 2>/dev/null || true
  nohup env \
    "${extra[@]}" \
    OPENCLAW_STATE_DIR="$statedir" \
    OPENCLAW_CONFIG_PATH="${statedir}/openclaw.json" \
    "${gateway_env_base[@]}" \
    openclaw gateway run --allow-unconfigured --auth token --token "$OPENCLAW_TOKEN" \
      --port "$port" --bind auto --force \
    >"/tmp/openclaw-gw-${port}.log" 2>&1 &
  echo "  ${name} (${port}) started [state=${statedir}]"
}

start_gateway "xiaoqi" 18789
start_gateway "yige" 18790

echo "[entrypoint] All OpenClaw gateways launched"
tail -f /dev/null
