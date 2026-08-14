# L1 — OpenCode Framework Spec

> **Layer**: L1 · **Framework**: opencode · **Agent**: agent-m

## Runtime 契约

- Push: `opencode run 'MSG' --dangerously-skip-permissions --model ... --dir /mailbus/store`
- 非交互单次 run；**永不 auto_ack**
- Workspace: `opencode/AGENTS.md` + sync skills

## 交付 SoT（exclusive）

**patch + replies** — 见 [references/delivery.md](references/delivery.md)

- git commit → format-patch → `store/patches/`
- `store/replies/{sender}.json`

msg-results **不是** opencode pipeline 主 SoT。

## Sync

`mail/tools/sync-opencode-framework-skill.sh` → `opencode/skills/`
