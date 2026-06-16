#!/bin/bash
# 从 Hermes 挂载目录读取 API Key（与 hermes 容器共用 /mnt/e/hermes-data/.hermes）

HERMES_DIR="${HERMES_SECRETS_DIR:-/hermes-secrets}"
CONFIG="${HERMES_DIR}/config.yaml"
DOTENV="${HERMES_DIR}/.env"

_yaml_provider_key() {
  local provider="$1"
  [ -f "$CONFIG" ] || return 0
  awk -v p="$provider" '
    /^providers:/ { inproviders=1; next }
    inproviders && $0 ~ "^  " p ":$" { inprov=1; next }
    inprov && /^    api_key:/ {
      sub(/^    api_key:[[:space:]]*/, "")
      gsub(/"/, "")
      print
      exit
    }
    inprov && /^  [a-z_0-9]+:/ { exit }
  ' "$CONFIG"
}

# 1) Hermes .env（如有）
if [ -f "$DOTENV" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$DOTENV"
  set +a
fi

# 2) Hermes config.yaml providers（完整 key 池）
_deepseek="$(_yaml_provider_key deepseek)"
_openai="$(_yaml_provider_key openai)"
_zhipu="$(_yaml_provider_key zhipu)"

[ -n "$_deepseek" ] && export DEEPSEEK_API_KEY="$_deepseek"
[ -n "$_openai" ] && export OPENAI_API_KEY="$_openai"
[ -n "$_zhipu" ] && export GLM_API_KEY="$_zhipu" && export ZHIPU_API_KEY="$_zhipu"

# OpenClaw 的 openai provider 走 OPENAI_API_KEY；DeepSeek 兼容模式兜底
export OPENAI_API_KEY="${OPENAI_API_KEY:-${DEEPSEEK_API_KEY:-}}"
export GLM_API_KEY="${GLM_API_KEY:-${OPENAI_API_KEY:-}}"
export ZHIPU_API_KEY="${ZHIPU_API_KEY:-${GLM_API_KEY:-}}"
export DASHSCOPE_API_KEY="${DASHSCOPE_API_KEY:-${ALIBABA_API_KEY:-}}"
export QWEN_API_KEY="${QWEN_API_KEY:-${DASHSCOPE_API_KEY:-}}"

if [ -z "${DEEPSEEK_API_KEY:-}" ] && [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "[openclaw] WARN: 未从 Hermes 读到 API Key，检查挂载 $HERMES_DIR" >&2
else
  echo "[openclaw] API keys loaded from Hermes ($HERMES_DIR)"
fi
