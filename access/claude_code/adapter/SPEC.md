# L1 — Claude Code Framework Spec

> **Layer**: L1 · **Framework**: claude_code · **Agents**: lingyun, lingyan

## Runtime 契约

- Push: `claude -p 'MSG' --permission-mode ...`（宿主机非 Docker）
- **无 auto_ack** · 完成 SoT：**msg-results**
- `CLAUDE.md` 由 sync 生成，勿手改指望持久

## 交付 SoT（exclusive）

`store/msg-results/{msg_id}.json` — 见 [references/delivery.md](references/delivery.md)

## Sync

`mail/tools/sync-claude-agent-context.py {agent}`
