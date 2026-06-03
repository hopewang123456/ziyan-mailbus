# Coding Agent Harness — 最终落地方案

## 背景
灵霄改代码会带出新 bug——修了 A 没验证 BCD，后面炸了。

## 方案方向（子言确认）
- ✅ **方案 A**（post-commit hook）起步
- → **方案 B**（CI）远期目标
- → **方案 C**（mailbus 手动）兜底

## 三层架构

```
git commit
  ↓
[post-commit hook] ─── 自动触发，跟 agent 无关
  ↓
┌─ 第1层：防回归 ──────────────────────┐
│ 跑 pytest → 对比 baseline            │
│ 有新增失败 → 提示灵霄                 │
└──────────────────────────────────────┘
  ↓
┌─ 第2层：AI 审质量 ───────────────────┐
│ 调 review.py 审 diff                 │
│ 跑 pylint + mypy 静态检查             │
│ semgrep 安全扫描（自定义规则）         │
│ 报告 → store/reports/                │
└──────────────────────────────────────┘
  ↓
┌─ 第3层：人工 review ─────────────────┐
│ mailbus 审批流                        │
│ 大力写 → 灵霄审                       │
│ 灵霄写 → 灵霄自审 + 灵瑾安全审计       │
│ 涉安模块 → 灵瑾                       │
│ 最终 → 小七验收                       │
└──────────────────────────────────────┘
```

## 分工

| 模块 | 谁做 | 谁审 |
|------|------|------|
| post-commit hook 脚本 | 大力 | 灵霄 |
| review.py 升级（pylint/mypy） | 大力 | 灵霄 |
| semgrep 自定义规则 | 大力 | 灵瑾 |
| review.py prompt 加密钥检测 | ✅ 灵瑾已改完 | 灵昭已确认 |
| auto-revert 安全（stash/精确回退/幂等） | 大力 | 灵瑾 |
| 涉安模块判定标准 → .clinerules | 灵瑾 | 灵昭已确认 |
| post-commit hook 安装到各项目 | 大力 | 小七验收 |
| mailbus 审批流 | 已有，不需要改 | — |

## 关键设计约束
1. **不侵入任何 agent 源码** — hook 是 git 原生，跟 Cline/OpenCode/Hermes 无关
2. **mailbus 保持独立** — review 报告推送 mailbus，但不依赖 mailbus 做门禁
3. **换 agent 不影响流程** — 装好 post-commit hook 就行
4. **允许跳过** — hook 失败时方案 C 兜底，不阻塞灵霄开发

## 验收标准
- [ ] 项目装 post-commit hook → commit 后自动触发 review
- [ ] review.py 跑 pylint + mypy + semgrep（自定义规则）+ 密钥检测
- [ ] 报告生成到 store/reports/
- [ ] 涉安模块判定标准写进 .clinerules
- [ ] auto-revert 安全保护（stash/精确回退/幂等）
- [ ] mailbus 审批流走通：review 报告推送 → reviewer 回复 APPROVE/REJECT
