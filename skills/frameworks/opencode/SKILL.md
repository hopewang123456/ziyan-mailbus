---
name: framework-runtime-opencode
description: >
  OpenCode 框架边界（大力/dali）。opencode run 非交互、无 auto_ack、patch+replies 交付。
always: true
type: framework_skill
layer: L1
framework: opencode
---

# OpenCode Framework Runtime

> agent: **dali（大力）** · workspace: `opencode/`

## Push 形态

```bash
opencode run 'MSG' --dangerously-skip-permissions --model deepseek/deepseek-chat --dir /mailbus/store
```

- **非交互**单次 run；**永不 auto_ack**
- mailbus 等 CLI 退出且 **msg-results / patch+replies** 落盘

## 10 条边界规则

1. 收到 push → 先写 `store/inbox/dali/ack.json`
2. 读 `store/msg-files/{id}.md`（完整工单）
3. 编码 + 测试 + 自审查（见 `opencode/AGENTS.md` SPARC）
4. 完成：**git commit → format-patch → store/replies/{sender}.json**
5. 禁止只聊天式「已完成」
6. cwd：`/mailbus/store` 或配置的 push.cwd
7. 不做方案设计/拆单（灵昭/小七职责）
8. 长输出 summary ≤200 字，细节在 patch / md
9. 共享协议 → `mailbus-file-protocol`
10. flash 日常编码；pro 长工单派 **lingyun（Claude Code）**

## 参考

| 主题 | 文件 |
|------|------|
| Token | [references/token.md](references/token.md) |
| 能力 | [references/capabilities.md](references/capabilities.md) |
| 交付 | [references/delivery.md](references/delivery.md) |

## 自检

- [ ] ack
- [ ] 测试通过
- [ ] patch 在 `store/patches/`
- [ ] replies 已写
