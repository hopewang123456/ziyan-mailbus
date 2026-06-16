#!/bin/bash
set -e
HERMES_HOME="${HERMES_HOME:-/home/hermes/.hermes}"

# 创建 profile（跳过已存在）
for args in \
  "lingzhao|你是灵昭 — 方案设计师。35岁，摩羯座，INTP。负责方案设计、架构决策。" \
  "lingjin|你是灵瑾 — 网络安全专家。28岁，天蝎座，INTP。负责安全审计。" \
  "lingxi|你是灵犀 — 技术雷达。31岁，射手座，ENTP。负责技术调研、前沿追踪。" \
  "lingjian|你是灵鉴 — 代码审查官。30岁，处女座，ISTJ。负责审查所有代码变更质量。" \
  "lingyan|你是灵验 — 测试工程师。28岁，巨蟹座，INTJ。负责功能测试、性能测试。" \
  "lingxun|你是灵巡 — 巡检官。35岁，金牛座，ISTJ。负责系统巡检、生成日报。"
do
  name="${args%%|*}"
  prompt="${args#*|}"
  hermes profile create "$name" --skip-if-exists 2>/dev/null || true
  mkdir -p "$HERMES_HOME/profiles/$name"
  cat > "$HERMES_HOME/profiles/$name/config.yaml" <<CONFIG
agent:
  max_turns: 90
  gateway_timeout: 1800
  api_max_retries: 3
  tool_use_enforcement: auto
  image_input_mode: auto
  disabled_toolsets: []
  clarify_timeout: 600
  system_prompt: '$prompt'
CONFIG
  echo "  ✅ $name"
done

# 启动 dashboard（后台）
for pair in "lingzhao:9120" "lingjin:9121" "lingxi:9122" "lingjian:9123" "lingyan:9124" "lingxun:9125"; do
  name="${pair%%:*}"
  port="${pair#*:}"
  hermes chat --profile "$name" --dashboard --port "$port" &
  echo "  🖥️  $name dashboard :$port"
done

echo "✅ 全部完成"
