---
name: framework-runtime-hermes
description: >
  Hermes CLI 框架边界（legacy type=hermes）。单次 -q push、notice 可 auto_ack。
  详细：references/{token,capabilities,delivery,memory}.md
always: true
type: framework_skill
layer: L1
framework: hermes
---

# Hermes Framework Runtime

> type: `hermes`（无 profile）。多 profile 见 `framework-runtime-hermes_profile`。

## Push 形态

```bash
hermes chat -q 'MSG' -Q --yolo [--model deepseek-chat]
```

- **单次查询** `-q`：一条 push = 一轮对话，无 mailbus 侧 session 续聊
- **notice** 可 auto_ack；**task** 须实质交付

## 10 条边界规则

1. 开工前：`python3 /path/to/.hermes/scripts/memory.py search "<关键词>"`
2. 默认 **flash**；Pro 需 mailbus 显式 `model_tier: pro`
3. 长工单读 `store/msg-files/{id}.md`，勿指望 CLI 正文含全文
4. 完成写 **msg-results** 或 chat 内可核验的 deliverable 路径
5. 不重复加载整份 identity；运行时上下文已注入
6. `--yolo` 已开：仍遵守团队 automation boundary（ADR-008）
7. cwd 通常为 `/mailbus/store` 或 profile 配置目录
8. 共享协议 → skill `mailbus-file-protocol`
9. 浏览器/agent-browser 在容器内可能禁用，勿依赖 UI 自动化
10. 不确定方案 → 回 lingzhao / xiaoqi，勿擅自改架构

## 参考文档

| 主题 | 文件 |
|------|------|
| Token | [references/token.md](references/token.md) |
| 能力边界 | [references/capabilities.md](references/capabilities.md) |
| 交付 | [references/delivery.md](references/delivery.md) |
| 记忆 | [references/memory.md](references/memory.md) |

## 自检

- [ ] memory search 已查
- [ ] msg-files 已读（若有）
- [ ] 交付可核验（非空泛「完成」）
