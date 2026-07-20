# L1 — Codex Framework Spec

> **Layer**: L1 · **Framework**: codex · **Agents**: lingxiao, lingjian

## Runtime 契约

- Push: Codex CLI 非交互；`approval_policy=never`（审查场景）
- cwd: `/mailbus/store` 或项目根
- **无 auto_ack**

## 交付 SoT（exclusive）

`store/msg-results/{msg_id}.json` — 见 [references/delivery.md](references/delivery.md)

## Sync

`mail/tools/sync_codex_agent_skills.py`
