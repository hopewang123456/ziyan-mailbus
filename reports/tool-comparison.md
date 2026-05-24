# 🔭 代码审查工具调研对比报告

> 调研人：灵犀 | 时间：2026-05-24
> 目标：为团队寻找可替代大壮（Aider）的代码审查工具，优先 CLI 驱动、可集成 mailbus、支持 DeepSeek

---

## 一、AI 驱动型 PR Review 工具

### 1. PR-Agent (Qodo) ⭐ 推荐
| 维度 | 说明 |
|------|------|
| **仓库** | github.com/The-PR-Agent/pr-agent (社区维护版，原 Qodo) |
| **语言** | Python |
| **评分** | ⭐⭐⭐⭐⭐ |
| **适合** | PR 级代码审查、自动生成 review comment |
| **优点** | • 支持 CLI 模式：`pr_agent --pr_url <url>` 直接调<br>• Docker 部署极简，一行命令<br>• 支持多种模型：OpenAI、Claude、**DeepSeek**<br>• 功能齐全：Describe/Review/Improve/Ask/Custom 等命令<br>• 支持 GitHub/GitLab/Bitbucket/Azure DevOps<br>• 社区活跃，文档完善 |
| **缺点** | • 设计目标偏 PR review，本地 diff review 需要包装一下<br>• Python 依赖较多（~50MB）<br>• 默认需要 GitHub token 配合 |
| **mailbus 集成** | ✅ 容易。CLI 模式 `pr_agent --pr_url <url>` 输出到 stdout，mailbus 直接调用即可 |
| **模型支持** | ✅ OpenAI / Claude / **DeepSeek** / Ollama 本地模型 / 自定义 |

### 2. deepseek-review (hustcer) ⭐
| 维度 | 说明 |
|------|------|
| **仓库** | github.com/hustcer/deepseek-review |
| **语言** | Nushell (Shell 脚本) |
| **评分** | ⭐⭐⭐ |
| **适合** | DeepSeek 深度用户的轻量 review 工具 |
| **优点** | • 原生 DeepSeek 支持<br>• 支持 GitHub Actions 和本地 CLI<br>• 可审查本地代码变更<br>• 轻量，shell 脚本实现 |
| **缺点** | • 依赖 Nushell（非标准 shell）<br>• 功能较基础，不如 PR-Agent 丰富<br>• 社区较小<br>• 文档不够完善 |
| **mailbus 集成** | ✅ 可以，但需要先安装 Nushell |
| **模型支持** | ✅ DeepSeek 专用 |

### 3. better-review (npm)
| 维度 | 说明 |
|------|------|
| **仓库** | npmjs.com/package/@xieziyu/better-review |
| **语言** | TypeScript / Node.js |
| **评分** | ⭐⭐ |
| **适合** | 交互式本地 PR review |
| **优点** | • 可驱动 Codex、Claude、pi 等 agent<br>• 浏览器 UI 展示结果<br>• 支持 gh CLI 推送 inline comment |
| **缺点** | • 需要浏览器环境<br>• 偏前端工作流<br>• 社区极小 |
| **mailbus 集成** | ❌ 较困难，依赖浏览器 UI |

### 4. CodeRabbit
| 维度 | 说明 |
|------|------|
| **评分** | ⭐⭐ |
| **适合** | GitHub/GitLab 原生 PR review |
| **优点** | • 功能强大，有 CLI 组件<br>• 支持 ast-grep 集成 |
| **缺点** | • 商业产品，免费版有限制<br>• 本地部署不友好<br>• 需要托管服务 |
| **mailbus 集成** | ❌ 不适用 |

---

## 二、静态分析工具（SAST / Linter）

### 5. Semgrep ⭐ 强烈推荐（组合使用）
| 维度 | 说明 |
|------|------|
| **仓库** | github.com/semgrep/semgrep (OCaml + Python) |
| **评分** | ⭐⭐⭐⭐⭐ |
| **适合** | 代码安全扫描 + 质量检查 |
| **优点** | • 本地运行，代码不上传<br>• 支持 30+ 语言<br>• 自定义规则非常灵活（模式即代码）<br>• CLI 优先，输出 JSON/stdout，管道友好<br>• 社区规则库丰富<br>• 可检测安全漏洞（OWASP Top 10）<br>• 与 reviewdog 集成方便 |
| **缺点** | • AST 级别的分析，不涉及语义理解<br>• 配置规则需要学习成本<br>• 不能替代 AI review（理解不了业务逻辑） |
| **mailbus 集成** | ✅ 非常容易。`semgrep scan --json path/to/code` → 解析 JSON → push |
| **模型支持** | ❌ 不需要模型（规则驱动） |

### 6. Ruff ⭐ 推荐
| 维度 | 说明 |
|------|------|
| **仓库** | github.com/astral-sh/ruff (Rust) |
| **评分** | ⭐⭐⭐⭐ |
| **适合** | Python 项目的代码风格 & 质量问题 |
| **优点** | • Rust 实现，极速（比 Flake8 快 100x）<br>• 直接替代 Flake8 + isort + pycodestyle 等工具链<br>• CLI 输出的 JSON 格式，管道友好<br>• 支持自动修复<br>• Astral 公司维护活跃 |
| **缺点** | • 仅支持 Python<br>• 不涉及安全漏洞<br>• 不能理解业务逻辑 |
| **mailbus 集成** | ✅ 非常容易。`ruff check --output-format json path/` |
| **模型支持** | ❌ 规则驱动 |

### 7. ast-grep
| 维度 | 说明 |
|------|------|
| **仓库** | github.com/ast-grep/ast-grep (Rust) |
| **评分** | ⭐⭐⭐ |
| **适合** | 结构化的代码搜索与模式匹配 |
| **优点** | • Rust 实现，极快<br>• 支持多语言 AST 模式匹配<br>• CLI 输出 JSON |
| **缺点** | • 主要做代码搜索，不是完整审查工具<br>• 需要编写 YAML 规则<br>• 偏工具链底层 |
| **mailbus 集成** | ✅ 容易 |
| **模型支持** | ❌ |

### 8. reviewdog ⭐ 推荐（作为胶水层）
| 维度 | 说明 |
|------|------|
| **仓库** | github.com/reviewdog/reviewdog (Go) |
| **评分** | ⭐⭐⭐⭐ |
| **适合** | 将各种 linter/分析工具的结果汇总成 review |
| **优点** | • 零配置接入任何输出标准格式的工具<br>• 支持 GitHub/GitLab CLI 发布 comment<br>• 支持本地模式（`-reporter=local`）<br>• 生成本地 diff 友好的 review |
| **缺点** | • 本身不分析代码，只是「搬运工」<br>• 需要搭配其他工具使用 |
| **mailbus 集成** | ✅ 容易。`reviewdog -reporter=local -ruler=true` |
| **模型支持** | ❌（但可以和任何工具组合） |

---

## 三、AI Coding Agent（已排除但仍列作参考）

| 工具 | 排除原因 |
|------|---------|
| **Aider** | 大壮在用，代码生成为主，非专门审查，不集成 mailbus |
| **OpenCode** | 大力在用，编码 agent，不适合审查场景 |
| **Claude Code** | 需要 Anthropic API，不适合自动化审查管道 |
| **OpenClaw** | 一哥在用，不适合审查 |
| **Codex CLI** | OpenAI 工程 agent，不适合 |

---

## 四、推荐方案

### 方案 A：PR-Agent + Semgrep 双引擎（推荐）
```
PR-Agent (AI review) ← diff 输入
 Semgrep (SAST scan) ← 代码库扫描
     ↓
 reviewdog (汇总)
     ↓
 mailbus 消息
```

**为什么这么搭：**
- **PR-Agent** 覆盖 AI 理解层面的审查（代码逻辑、可读性、最佳实践）
- **Semgrep** 覆盖规则层面的安全 & 质量问题
- **reviewdog** 作为胶水层，统一输出格式
- 两个都支持 DeepSeek（PR-Agent 配置 `--model deepseek`）
- 全部 CLI 驱动，mailbus 一行命令就能调

### 方案 B：轻量版（适合简单项目）
```
Ruff (Python 项目) 或 semgrep (多语言)
  → reviewdog
  → mailbus
```
无 AI 调用，纯规则驱动，零成本，毫秒级反馈。

### 方案 C：全量版
```
PR-Agent (AI) → diff 分析
Semgrep (SAST) → 安全扫描
Ruff / ast-grep → 代码风格/结构检查
    ↓
reviewdog (汇总)
    ↓
mailbus 通知大壮/灵昭
```

---

## 五、集成 mailbus 的示例

以 PR-Agent 为例，mailbus 中的调用方式：

```json
{
  "type": "code_review",
  "content": "pr_agent --pr_url https://github.com/xxx/pull/42 --model deepseek-v4-pro",
  "to": "dazhuang"
}
```

或通过 shell 包装：

```bash
# mailbus 调用代码审查
git diff HEAD~1 | pr_agent --diff-file - --model deepseek-v4-pro
# 输出到 stdout → mailbus 捕获 → 推给相关 agent
```

---

## 六、总结

| 工具 | 核心价值 | mailbus 集成 | DeepSeek | 推荐度 |
|------|---------|:-----------:|:--------:|:-----:|
| **PR-Agent** | AI PR Review | ✅ 易 | ✅ | ⭐⭐⭐⭐⭐ |
| **Semgrep** | SAST 安全扫描 | ✅ 易 | N/A | ⭐⭐⭐⭐⭐ |
| **Ruff** | Python 质量检查 | ✅ 易 | N/A | ⭐⭐⭐⭐ |
| **reviewdog** | 胶水汇总层 | ✅ 易 | N/A | ⭐⭐⭐⭐ |
| deepseek-review | 轻量 DeepSeek review | ✅ 可 | ✅ | ⭐⭐⭐ |
| ast-grep | 结构化代码搜索 | ✅ 可 | N/A | ⭐⭐⭐ |
| better-review | 交互式 PR review | ❌ 难 | ❌ | ⭐⭐ |
| CodeRabbit | 托管 PR review | ❌ | ❌ | ⭐⭐ |

**我的建议：** 先用 **方案 A**（PR-Agent + Semgrep），两个都 CLI 驱动、都支持 mailbus 集成、都不需要 GPU。PR-Agent 配 DeepSeek 做 AI 审查，Semgrep 做安全扫描。如果团队觉得太重，**方案 B**（纯静态分析）也是一个不错的选择。

要不要我把方案 A 的集成脚本写出来，方便小七配置 mailbus 调度？
