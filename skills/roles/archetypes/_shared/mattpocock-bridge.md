# SPARC ↔ Matt Pocock Skills 映射

> 编码相关工种：`coding-executor`、`coding-pro`；测试用 `diagnose`/`triage`；审查用 `zoom-out`/`grill-with-docs`

## 映射表

| SPARC 阶段 | 负责工种 | Matt skill | 产物 |
|------------|----------|------------|------|
| S Specification | spec-designer | `/grill-with-docs`, `/to-prd` | PRD、CONTEXT.md、ADR |
| P Pseudocode | orchestrator | `/to-issues` | 垂直切片 issues |
| A Architecture | coding-executor/pro | `/grill-with-docs`（技术确认） | 架构确认 checklist |
| R Refinement | coding-executor/pro | `/tdd`, `/diagnose` | patch + tests |
| C Completion | orchestrator | `/triage` | 验收状态 |

## 安装

```bash
npx skills@latest add mattpocock/skills
```

本地镜像：`openclaw_space/matt-skills/`

## Per-repo 配置

新项目首次：`/setup-matt-pocock-skills` → 生成 `docs/agents/{issue-tracker,triage-labels,domain}.md`

## 与团队 TDD 关系

- **首选**：matt `/tdd`（行为测试、垂直切片）
- **Fallback**：Hermes/Superpowers TDD skill

详细指南 → `openclaw_space/matt-pocock-skills-guide.md`
