---
name: framework-runtime-claude_code
description: >
  Claude Code 框架边界（lingyun/lingyan）。宿主机 claude -p、msg-results SoT、permission_mode 分角色。
always: true
type: framework_skill
layer: L1
framework: claude_code
---

# Claude Code Framework Runtime

> agents: **lingyun**（pro 编码）, **lingyan**（测试）· 宿主机非 Docker

## Push 形态

```bash
claude -p 'MSG' --permission-mode acceptEdits ...   # lingyun
claude -p 'MSG' --permission-mode dontAsk --allowedTools "Bash,Read,Glob,Grep" ...  # lingyan
```

- **无 auto_ack** · 完成 SoT：**msg-results**
- `CLAUDE.md` 由 sync 生成，**勿手改指望持久**

## 10 条边界规则

1. ack → `store/inbox/{agent}/ack.json`
2. 读 `msg-files/{id}.md` 全文
3. 写 `store/msg-results/{id}.json`（无 = 未完成）
4. lingyun：`acceptEdits` 可改代码；lingyan：**仅** Bash/Read/Glob/Grep
5. lingyan 不写业务代码，只测与报告
6. 启动前 sync：`sync-claude-agent-context.py {agent}`
7. skills 在 `claude_home/skills`，按需 Read
8. push.cwd 通常 `E:\ai_tools` 或项目根
9. 共享协议 → `mailbus-file-protocol`
10. 勿用 Claude Desktop 做 mailbus 任务（用 CLI `-p`）

## 参考

| 主题 | 文件 |
|------|------|
| Token | [references/token.md](references/token.md) |
| 能力 | [references/capabilities.md](references/capabilities.md) |
| 交付 | [references/delivery.md](references/delivery.md) |

## 自检

- [ ] msg-results 已写
- [ ] lingyan 未改 src（除非工单允许）
