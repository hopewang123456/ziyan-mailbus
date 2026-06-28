# L1 — OpenClaw Framework Spec

> **Layer**: L1 · **Framework**: openclaw · **Agents**: xiaoqi, yige

## Runtime 契约

- Push: `openclaw agent --local --agent <id> --message 'MSG'`
- `OPENCLAW_STATE_DIR` 按 agent 隔离
- notice 可 **auto_ack**；task 须实质回复
- Workspace: AGENTS.md + SOUL.md + USER.md + HEARTBEAT.md（OpenClaw 约定）

## 交付 SoT（exclusive）

见 [references/delivery.md](references/delivery.md)

## 编码纪律

OpenClaw workspace 内涉及编码时 → [references/coding-discipline.md](references/coding-discipline.md)

## Sync

`mail/tools/sync-openclaw-framework-skill.sh` → `openclaw_space/skills/`
