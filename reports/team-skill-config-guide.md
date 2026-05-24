# 🛠️ 团队 Skill 配置指南

> 编制：灵犀 | 时间：2026-05-24
> 
> 本文件说明每个角色应该配置什么 skill、怎么配、在哪里配。
> 配置好了才叫"持有了 skill"——不然只是存在目录里。

---

## 🦊 灵犀（我）— 前沿技术研究员

### 需要配置的 skill（12 个）

| Skill | 配置方式 | 说明 |
|:------|:---------|:------|
| `research/ai-hot` | 内置，已启用 | 每天扫 AI 热点 ⭐ |
| `research/notebooklm-py` | pip install + login | 调研报告转播客/PPT |
| `research/ai-engineering-from-scratch` | 本地 skill，已安装 | 理论补充 |
| `research/blogwatcher` | 内置，已启用 | RSS 监控 |
| `research/arxiv` | 内置，已启用 | 论文搜索 |
| `note-taking/obsidian` | 内置，已启用 | 笔记 |
| `research/llm-wiki` | 内置，已启用 | 知识库 |
| `research/polymarket` | 内置，已启用 | 市场趋势 |
| `creative/sketch` | 内置，已启用 | 报告配图 |
| `software-development/codegraph` | 本地 skill | 调研时快速看代码 |
| `software-development/cli-anything` | 本地 skill | 新工具 CLI 化评估 |
| `software-development/cua-computer-use` | 本地 skill | Desktop Agent 趋势 |

### 不需要配的（放公共库）

creative 类 19 个中只持 1 个（sketch），其他需要时临时 `skill_view`。

---

## 🪷 灵昭 — 架构师 / 决策者

### 需要配置的 skill（10 个）

| Skill | 配置方式 | 说明 |
|:------|:---------|:------|
| `autonomous-ai-agents/multi-agent-team-workflow` | 本地 skill | 团队协作总指挥 |
| `software-development/writing-plans` | 内置 | 出方案文档 |
| `research/notebooklm-py` | pip install + login | 方案转宣讲材料 |
| `research/huashu-design` | npx skills add | 方案出高保真原型 |
| `research/ai-engineering-from-scratch` | 本地 skill | 决策理论支撑 |
| `autonomous-ai-agents/hermes-agent` | 内置 | Agent 系统配置 |
| `software-development/requesting-code-review` | 内置 | 审查流程把控 |
| `github/github-workflow` | 新配 | GitHub 操作 |
| `productivity/linear` | 内置 | 项目管理 |
| `software-development/coding-agents` | 新配 | 了解各 Agent 能力 |

### 不需要配的

不需要关心 creative/编码类 skill，不持。

---

## 🚀 灵霄 — 技术负责人 / 架构师

### 需要配置的 skill（13 个）

| Skill | 配置方式 | 说明 |
|:------|:---------|:------|
| `software-development/codegraph` | 本地 skill | 架构分析 ⭐ |
| `software-development/understand-anything` | npm / plugin install | 代码可视化 ⭐ |
| `software-development/cli-anything` | 本地 skill | 工具 CLI 化 |
| `research/huashu-design` | npx skills add | 架构图可视化 |
| `research/ai-engineering-from-scratch` | 本地 skill | Infra/Agent 架构 |
| `mcp/native-mcp` | 内置 | MCP 协议接入 |
| `software-development/cua-computer-use` | 本地 skill | 数字孪生评估 ⭐ |
| `software-development/spike` | 内置 | 技术验证 |
| `software-development/python-debugpy` | 内置 | 调试 |
| `software-development/systematic-debugging` | 内置 | 根因分析 |
| `software-development/writing-plans` | 内置 | 出技术方案 |
| `creative/architecture-diagram` | 内置 | 画架构图 |
| `software-development/coding-agents` | 新配 | 编码 Agent 编排 |

### 参考学习（不配 skill）

- `obra/superpowers` — workflow 架构思路
- `rohitg00/agentmemory` — 记忆系统评估

---

## 💪 大力 — 编码工程师

### 需要配置的 skill（10 个）

| Skill | 配置方式 | 说明 |
|:------|:---------|:------|
| `autonomous-ai-agents/coding-agents` | 新配 | **编码 Agent 日常 ⭐** |
| `software-development/cli-anything` | 本地 skill | 工具自动化 |
| `research/ai-engineering-from-scratch` | 本地 skill | Phase 11-16 |
| `software-development/test-driven-development` | 内置 | TDD |
| `software-development/systematic-debugging` | 内置 | 调试 |
| `software-development/spike` | 内置 | 技术验证 |
| `software-development/python-debugpy` | 内置 | Python 调试 |
| `github/github-workflow` | 新配 | PR 流程 |
| `research/notebooklm-py` | pip install | 文档转思维导图 |
| `software-development/understand-anything` | npm / plugin | 新手上手项目 |

### 必须安装的外部依赖

```bash
# Coding Agent
npm i -g @anthropic-ai/claude-code
npm i -g opencode-ai

# 配置 CLAUDE.md（Karpathy 秘籍）
cp andrej-karpathy-skills/CLAUDE.md ~/.claude/CLAUDE.md
```

---

## 🤖 审查流程（review.py + Semgrep）

### 需要配置的 skill（5 个）

| Skill | 配置方式 | 说明 |
|:------|:---------|:------|
| `software-development/requesting-code-review` | 内置 | PR 审查核心 ⭐ |
| `software-development/codegraph` | 本地 skill | 调用链分析 |
| `software-development/ai-security-tool-evaluation` | 本地 skill | 安全评估 |
| `software/semgrep`（外部工具） | pip install semgrep | SAST 扫描 ⭐ |
| `research/ai-engineering-from-scratch` | 本地 skill | 安全对齐 |

### 外部依赖

```bash
pip install semgrep
# review.py 是自动化脚本，由小七维护
```

---

## 🦅 一哥 — 首席运营家

### 需要配置的 skill（10 个）

| Skill | 配置方式 | 说明 |
|:------|:---------|:------|
| `research/huashu-design` | npx skills add | **运营核心 ⭐** |
| `research/notebooklm-py` | pip install + login | **内容多格式输出 ⭐** |
| `research/ai-hot` | 内置 | 行业热点/选题 |
| `research/easy-vibe` | 本地 skill | **零代码做运营工具 ⭐** |
| `research/blogwatcher` | 内置 | 行业动态 |
| `creative/ascii-video` | 内置 | 创意视频 |
| `creative/ascii-art` | 内置 | 创意内容 |
| `creative/pixel-art` | 内置 | 复古视觉 |
| `media/heartmula` | 内置 | AI 音乐生成 |
| `social-media/xurl` | 内置 | 社媒分发 |

### 安装依赖

```bash
pip install notebooklm-py
notebooklm login
npx skills add alchaincyf/huashu-design
```

### 补充工具

- **Present AI**（notebooklm-py 备选）— 纯 PPT 场景: `git clone https://github.com/allweonedev/presentation-ai`

---

## 🐱 小七 — 调度 / 运维

### 需要配置的 skill（9 个）

| Skill | 配置方式 | 说明 |
|:------|:---------|:------|
| `devops/kanban-orchestrator` | 内置 | 任务分解调度 ⭐ |
| `devops/kanban-worker` | 内置 | 任务执行 |
| `autonomous-ai-agents/hermes-agent` | 内置 | Agent 系统管理 |
| `productivity/linear` | 内置 | 项目管理 |
| `note-taking/obsidian` | 内置 | 文档维护 |
| `devops/webhook-subscriptions` | 内置 | 事件驱动 |
| `github/github-workflow` | 新配 | GitHub 操作 |
| `software-development/cli-anything` | 本地 skill | 工具接入管道 |
| `mcp/native-mcp` | 内置 | MCP 服务管理 |

---

## 📋 谁需要安装什么外部依赖

| 依赖 | 安装命令 | 需要的人 |
|:-----|:---------|:---------|
| `notebooklm-py` | `pip install notebooklm-py && notebooklm login` | 🦊 灵犀 · 🪷 灵昭 · 🦅 一哥 |
| `huashu-design` | `npx skills add alchaincyf/huashu-design` | 🦅 一哥 · 🪷 灵昭 · 🚀 灵霄 |
| `claude-code` | `npm i -g @anthropic-ai/claude-code` | 💪 大力 |
| `opencode` | `npm i -g opencode-ai` | 💪 大力 |
| `andrej-karpathy-skills` | `cp CLAUDE.md ~/.claude/CLAUDE.md` | 💪 大力 |
| `semgrep` | `pip install semgrep` | 🤖 审查流程 |
| `understand-anything` | `npx understand-anything` 或 Claude 插件 | 🚀 灵霄 · 💪 大力 |
| `present-ai` | `git clone ...`（按需） | 🦅 一哥（备选） |
| `cua` | `pip install cua`（需 Docker） | 🚀 灵霄（评估用） |

---

## 📦 公共库 skill（不需配置，临时 skill_view 即可）

这些 skill 不绑定任何角色，谁需要谁调：

- `creative/baoyu-comic` · `baoyu-infographic` — 知识漫画/信息图
- `creative/comfyui` · `touchdesigner-mcp` — AI 生成/实时视觉
- `creative/p5js` · `manim-video` — 创意编码/数学动画
- `creative/design-md` · `popular-web-designs` · `pretext` — 设计规范/风格库
- `creative/ideation` · `songwriting-and-ai-music` · `humanizer` — 创意/文案
- `creative/excalidraw` — 手绘风格图
- `gaming/minecraft-modpack-server` · `pokemon-player` — 游戏（玩）
- `email/himalaya` — 邮箱操作
- `smart-home/openhue` — 智能灯
- `media/gif-search` · `songsee` · `spotify` · `youtube-content` — 媒体工具
- `productivity/airtable` · `google-workspace` · `maps` · `nano-pdf` · `notion` · `ocr-and-documents` · `teams-meeting-pipeline` — 办公工具
- `mlops/*`（9 个）— ML 基础设施（有需要时再调）
- `red-teaming/godmode` — 特殊用途
- `apple/*`（5 个）— macOS 专用
- `data-science/jupyter-live-kernel` — 数据科学
