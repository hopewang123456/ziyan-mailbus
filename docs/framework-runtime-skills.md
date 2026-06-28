# Runtime Skill 层（L0–L3 Agent 分层）

> 权威说明：[`agent-layer-spec.md`](agent-layer-spec.md) · 运行时 SoT：`store/rules/agent-layer-spec.md`

## 四层结构

```
mailbus Core (agent_id + role_type)
        ↓
Adapter 层 (agent_adapters.py — push CLI / auto_ack)
        ↓
L0 通用边界 (agent-universal + mailbus-file-protocol)
        ↓
L1 框架边界 (framework-runtime-{framework})
        ↓
L2 工种边界 (role-{archetype} + role-overlay-{agent})
        ↓
L3 领域 Skill (TDD、tarot、patroller…)
```

## 资源

| 路径 | 说明 |
|------|------|
| [`skills/common/`](../skills/common/) | L0 共享协议 |
| [`skills/frameworks/`](../skills/frameworks/) | L1 框架 runtime |
| [`skills/roles/`](../skills/roles/) | L2 工种 archetype + overlay |
| [`access/`](../access/) | agent.json + adapter 契约 |
| [`docs/agent-layer-spec.md`](agent-layer-spec.md) | 分层模型 |
| `store/agents/json/skills-index.json` | 每 agent 的 layer skills 索引 |
| `tools/patch-skills-index-framework.py` | 幂等补全 L0–L2 |
| `tools/validate-agent-layers.py` | 分层校验 |
| `tools/sync-all-agent-layers.py` | 一键 sync 全部 workspace（OpenCode/OpenClaw/Claude） |
| `lib/framework_skills.py` | resolve + install |

## Sync 入口

| 框架 | 脚本 |
|------|------|
| codex | `tools/sync_codex_agent_skills.py` |
| claude_code | `tools/sync-claude-agent-context.py` |
| opencode | `tools/sync-opencode-framework-skill.sh` |
| openclaw | `tools/sync-openclaw-framework-skill.sh` |
| hermes_profile | `tools/sync-hermes-framework-skill.sh` |
| **全部** | `tools/sync-all-agent-layers.py` |

容器挂载：`mail/skills` + `mail/access` + `mail/rules` → 容器内 sync resolve

## 命名空间

- **`mail/skills/`** — L0/L1/L2 skill 包 SoT
- **`mail/rules/`** — 行为规范 SoT（common / frameworks / roles）
- **勿混淆** `access/external-tools/adapters/` — Coze/Dify/webhook
