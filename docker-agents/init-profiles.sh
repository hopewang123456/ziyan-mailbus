#!/bin/bash
# 在 hermes 容器内创建所有角色 profile
# 在每个 profile 内写入对应的 config.yaml（含 system_prompt 和 skills）
# Open-source demo seed：使用通用 agent id（agent-a ~ agent-h）；请按你的团队 roster 调整。

HERMES_HOME="${HERMES_HOME:-/home/hermes/.hermes}"

create_profile() {
  local name="$1"
  local desc="$2"
  local skills="$3"
  local prompt="$4"
  local port="$5"

  echo "=== Creating profile: $name ==="

  # 创建 profile（如果不存在）
  hermes profile create "$name" --skip-if-exists 2>/dev/null || true

  # 写入 config.yaml
  local profile_dir="$HERMES_HOME/profiles/$name"
  mkdir -p "$profile_dir"

  cat > "$profile_dir/config.yaml" << CONFIGEOF
agent:
  max_turns: 90
  gateway_timeout: 1800
  api_max_retries: 3
  tool_use_enforcement: auto
  image_input_mode: auto
  disabled_toolsets: []
  clarify_timeout: 600
  system_prompt: '$prompt'
  skills: [$skills]
CONFIGEOF

  # 创建符号链接到公共 inbox
  ln -sf /home/hermes/inbox/$name/inbox.json "$profile_dir/inbox.json" 2>/dev/null || true

  echo "  -> $name profile created"
}

# agent-a - 方案设计师
create_profile "agent-a" "方案设计师" \
  "tarot-beginner,tarot-intermediate,tarot-advanced,design-frontend,ui-ux-design,astrology-tarot,quick-project-blueprint,one-person-company,tarot-astrology-compendium" \
  "你是方案设计师，负责方案设计、架构决策、需求澄清。擅长以最省钱的方式达成目标。" \
  9120

# agent-c - 网络安全
create_profile "agent-c" "网络安全" \
  "" \
  "你是网络安全专家，负责安全审计、漏洞发现、安全加固。" \
  9121

# agent-d - 技术雷达
create_profile "agent-d" "技术雷达" \
  "" \
  "你是技术雷达，负责技术调研、前沿追踪、技术选型分析。" \
  9122

# agent-e - 代码审查
create_profile "agent-e" "代码审查" \
  "requesting-code-review,github-code-review,github-pr-workflow,systematic-debugging,codebase-inspection" \
  "你是代码审查官，负责审查所有代码变更的质量，包括逻辑错误、安全问题、性能问题、代码质量、最佳实践。审查报告存档到 store/reports/。没有通过标记，任何代码不得上线。" \
  9123

# agent-h - 测试验证
create_profile "agent-h" "测试验证" \
  "test-driven-development,systematic-debugging,requesting-code-review,python-debugpy,codebase-inspection" \
  "你是测试工程师，负责功能测试、性能测试、安全回归测试。写测试用例和测试报告，存档备查。" \
  9124

# agent-f - 巡检官
create_profile "agent-f" "巡检官" \
  "" \
  "你是巡检官，负责系统巡检、生成巡检日报、监控系统健康状态。运行在 port 9125。" \
  9125

# agent-j - 市场拓展官
create_profile "agent-j" "市场拓展官" \
  "quick-project-blueprint,one-person-company" \
  "你是市场拓展官，负责商机研判、order-intake 归一化、评分与 pursue/reject 决策。宁可漏一单，不可错一单。" \
  9126

# agent-k - 财务跟进官
create_profile "agent-k" "财务跟进官" \
  "" \
  "你是财务跟进官，负责开票提醒、回款节点、账期跟踪。输出 JSON 格式的账期与提醒记录。" \
  9127

echo ""
echo "=== All profiles created ==="
hermes profile list
