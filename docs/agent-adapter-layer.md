# Agent Adapter 层（L0–L3 分层）

> **已更新 2026-06-24** — 原「三层 runtime skill」扩展为 L0–L3。公开镜像：[`mail/docs/agent-layer-spec.md`](../../docs/agent-layer-spec.md)

## 栈

```
mailbus Core (config.json, inbox, pipeline)
        ↓
Adapter 层 (lib/agent_adapters.py — push CLI / auto_ack)
        ↓
L0 agent-universal + mailbus-file-protocol
        ↓
L1 framework-runtime-{framework}
        ↓
L2 role-{archetype} + role-overlay-{agent}
        ↓
L3 domain skills（按需）
```

## 资源

| 路径 | 说明 |
|------|------|
| `mail/adapters/` | L0 + L1 skill 库 |
| `mail/roles/` | L2 archetype + overlay |
| `store/agents/json/skills-index.json` | 每 agent 组合索引 |
| `tools/patch-skills-index-framework.py` | 幂等补全 L0–L2 |
| `tools/validate-agent-layers.py` | 分层校验 |
| `tools/sync_framework_workspace_skills.py` | OpenCode/OpenClaw workspace sync |

## 废弃

- inline mailbus 规则写入 `AGENTS.md` / `identities/*.md` — **禁止**（用 sync skills）
- `mail/STANDARD_PROCEDURE.md` — 已弃用，仅历史镜像
- `openclaw_space/*/MAILBUS.md` — 已弃用，指向 L0/L1 skills
- `mail/rules/`（非 store）— 历史镜像，改 `store/rules/`
