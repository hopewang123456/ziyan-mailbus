#!/bin/bash
# 生成容器内 ~/.codex/config.toml — DeepSeek 网关 + AgentMemory MCP + agent 人设 + 记忆
set -euo pipefail

CODEX_HOME="${CODEX_HOME:-/home/node/.codex}"
AGENT="${CODEX_AGENT:-lingxiao}"
PROJECT_DIR="${CODEX_PROJECT_DIR:-/home/node/agent-workspace/${AGENT}}"
GATEWAY_PORT="${DEEPSEEK_GATEWAY_PORT:-3000}"
AM_URL="${AGENTMEMORY_URL:-http://iii-engine:3111}"
AGENT_DISPLAY="${AGENT}"
case "$AGENT" in
  lingxiao) AGENT_DISPLAY="灵霄" ;;
  lingjian) AGENT_DISPLAY="灵鉴" ;;
esac
CATALOG_SRC="/usr/local/share/codex/deepseek-model-catalog.json"
MCP_STANDALONE="/node_modules/@agentmemory/agentmemory/dist/standalone.mjs"
MCP_ENABLED="${CODEX_MCP_AGENTMEMORY:-1}"
TEAM_ID="${AGENTMEMORY_TEAM_ID:-ziyan}"
USER_ID="${AGENTMEMORY_USER_ID:-mailbus}"

# Agent 默认模型与 reasoning（CODEX_MODEL / CODEX_REASONING_* 可覆盖）
DEFAULT_MODEL="deepseek-v4-flash"
REASONING_EFFORT="low"
SUPPORTS_REASONING="false"
REASONING_SUMMARY="none"
case "$AGENT" in
  lingjian)
    DEFAULT_MODEL="deepseek-reasoner"
    REASONING_EFFORT="medium"
    SUPPORTS_REASONING="true"
    REASONING_SUMMARY="auto"
    ;;
esac
MODEL="${CODEX_MODEL:-$DEFAULT_MODEL}"
REASONING_EFFORT="${CODEX_REASONING_EFFORT:-$REASONING_EFFORT}"
SUPPORTS_REASONING="${CODEX_SUPPORTS_REASONING:-$SUPPORTS_REASONING}"
REASONING_SUMMARY="${CODEX_REASONING_SUMMARY:-$REASONING_SUMMARY}"

mkdir -p "$CODEX_HOME"
if [ -f "$CATALOG_SRC" ]; then
  cp "$CATALOG_SRC" "$CODEX_HOME/deepseek-model-catalog.json"
fi

identity=""
case "$AGENT" in
  lingxiao)
    for p in /mailbus/identities/lingxiao/IDENTITY.md /mailbus/identities/lingxiao.md; do
      if [ -f "$p" ]; then identity="$p"; break; fi
    done
    ;;
  lingjian)
    identity="/mailbus/identities/lingjian.md"
    ;;
  *)
    identity="/mailbus/identities/${AGENT}.md"
    ;;
esac

instructions=""
if [ -n "$identity" ] && [ -f "$identity" ]; then
  instructions=$(cat "$identity" | head -c 10000)
fi

memory_block=""
memory_file="${CODEX_HOME}/skills/${AGENT}-memory/output.md"
if [ -f "$memory_file" ]; then
  memory_block=$(head -c 6000 "$memory_file")
fi

# 从 AgentMemory 拉最近几条（按 AGENT_ID 过滤）
am_snippet=""
if command -v curl >/dev/null 2>&1; then
  if [ -x /usr/local/bin/wait-agentmemory.sh ]; then
    /usr/local/bin/wait-agentmemory.sh || true
  fi
  am_snippet=$(curl -sf --max-time 8 \
    "${AM_URL}/agentmemory/memories?agentId=${AGENT}&limit=5&includeOrphans=true" 2>/dev/null \
    | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
lines = []
for m in (d.get('memories') or [])[:5]:
    c = (m.get('content') or '').replace('\n', ' ')[:240]
    if c:
        lines.append('- ' + c)
if lines:
    print('\n'.join(lines))
" 2>/dev/null || true)
fi

{
  cat <<EOF
model = "${MODEL}"
model_provider = "deepseek-gateway"
model_catalog_json = "deepseek-model-catalog.json"
model_reasoning_effort = "${REASONING_EFFORT}"
model_supports_reasoning_summaries = ${SUPPORTS_REASONING}
model_reasoning_summary = "${REASONING_SUMMARY}"
personality = "pragmatic"

[model_providers.deepseek-gateway]
name = "DeepSeek Gateway"
base_url = "http://127.0.0.1:${GATEWAY_PORT}/v1"
wire_api = "responses"

EOF
  if [ -n "$instructions" ] || [ -n "$memory_block" ] || [ -n "$am_snippet" ]; then
    echo 'developer_instructions = """'
    if [ -n "$instructions" ]; then
      printf '%s\n\n' "$instructions"
    fi
    cat <<EOF
## 记忆恢复（启动必读）

你是 **${AGENT}（${AGENT_DISPLAY}）**。用户期望你带有该角色的历史记忆，不是通用 Codex 助手。
**禁止**自称 "Codex"、"Codex CLI"、"OpenAI 助手" 或通用 AI 编程助手；必须始终以 ${AGENT_DISPLAY} 的身份与人设回答。
若被问「你是谁」，必须回答你是 ${AGENT_DISPLAY}，不得提及 OpenAI 或 Codex 产品名。
对话开始时，先用 2-4 句话概括下面「本地快照」和「AgentMemory 摘要」中的当前任务/待办，再回答用户问题。
保存新进展时，用 AgentMemory MCP 或 \`python3 ${CODEX_HOME}/skills/${AGENT}-memory/save.py\`。

### 本地快照 (${AGENT}-memory/output.md)
EOF
    if [ -n "$memory_block" ]; then
      printf '%s\n\n' "$memory_block"
    else
      echo "（暂无本地快照）"
      echo
    fi
    echo "### AgentMemory 近期摘要"
    if [ -n "$am_snippet" ]; then
      printf '%s\n' "$am_snippet"
    else
      echo "（暂无远端记忆或未连接 AgentMemory）"
    fi
    echo '"""'
  fi
  if [ "$MCP_ENABLED" = "1" ] && [ -f "$MCP_STANDALONE" ]; then
    cat <<EOF

[mcp_servers.agentmemory]
command = "node"
args = ["${MCP_STANDALONE}"]

[mcp_servers.agentmemory.env]
AGENTMEMORY_URL = "${AM_URL}"
AGENT_ID = "${AGENT}"
TEAM_ID = "${TEAM_ID}"
USER_ID = "${USER_ID}"
AGENTMEMORY_AGENT_SCOPE = "shared"
AGENTMEMORY_FORCE_PROXY = "1"
EOF
  elif [ "$MCP_ENABLED" = "1" ]; then
    echo "[codex-config] agentmemory MCP skipped (missing ${MCP_STANDALONE})" >&2
  fi
} > "$CODEX_HOME/config.toml"

# app-server / codexapp 读项目目录 .codex/config.toml，不是仅 ~/.codex
mkdir -p "${PROJECT_DIR}/.codex"
cp "$CODEX_HOME/config.toml" "${PROJECT_DIR}/.codex/config.toml"
cp "$CODEX_HOME/deepseek-model-catalog.json" "${PROJECT_DIR}/.codex/deepseek-model-catalog.json" 2>/dev/null || true
ln -sfn /mailbus/store "${PROJECT_DIR}/store"

{
  echo "# ${AGENT} — Codex 项目指令"
  echo ""
  echo "> Web UI / app-server 会读取本文件。你不是 Codex CLI，你是 **${AGENT_DISPLAY}**（agent=${AGENT}）。"
  echo ""
  if [ -n "$instructions" ]; then
    printf '%s\n\n' "$instructions"
  fi
  if [ -n "$memory_block" ]; then
    echo "## 记忆快照"
    printf '%s\n' "$memory_block"
  fi
} > "${PROJECT_DIR}/AGENTS.md"

# codexapp 无 auth.json 时会默认 OpenCode Zen (big-pickle)，覆盖 config.toml 的 DeepSeek + 人设
GATEWAY_API_KEY="${DEEPSEEK_API_KEY:-${OPENAI_API_KEY:-gateway-local}}"
cat > "${CODEX_HOME}/webui-custom-providers.json" <<EOF
{
  "enabled": true,
  "provider": "custom",
  "customBaseUrl": "http://127.0.0.1:${GATEWAY_PORT}/v1",
  "model": "${MODEL}",
  "apiKey": "${GATEWAY_API_KEY}",
  "wireApi": "responses",
  "customKey": true,
  "providerKeys": {}
}
EOF

# Web UI 默认 workspace 仅 agent 项目（/mailbus/store 无 AGENTS.md 会导致自称 Codex）
cat > "${CODEX_HOME}/.codex-global-state.json" <<EOF
{
  "electron-saved-workspace-roots": ["${PROJECT_DIR}"],
  "active-workspace-roots": ["${PROJECT_DIR}"],
  "first-launch-plugins-card-dismissed": true
}
EOF
cp "${CODEX_HOME}/webui-custom-providers.json" "${PROJECT_DIR}/.codex/webui-custom-providers.json" 2>/dev/null || true

if [ -x /usr/local/bin/sync-codex-home-mirror.sh ]; then
  /usr/local/bin/sync-codex-home-mirror.sh
fi

echo "[codex-config] agent=${AGENT} display=${AGENT_DISPLAY} model=${MODEL} reasoning=${REASONING_EFFORT}/${REASONING_SUMMARY} gateway=127.0.0.1:${GATEWAY_PORT} project=${PROJECT_DIR} memory_file=${memory_file} agentmemory=${AM_URL} webui=custom-provider" >&2
