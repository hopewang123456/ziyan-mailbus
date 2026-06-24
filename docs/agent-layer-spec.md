# Agent 分层 Spec（L0–L3）

> **运行时 SoT**: `store/rules/agent-layer-spec.md`（与本文同步）  
> **公开镜像**: `mail/docs/agent-layer-spec.md`

## 组合模型

```
Agent 合规 = L0 universal + mailbus-file-protocol
           + L1 framework-runtime-{type}
           + L2 role-{archetype} + role-overlay-{agent_id}
           + identity（人设，非边界 spec）
           + L3 domain skills（按需）
```

## 各层职责

| Layer | 包路径 | 内容 |
|-------|--------|------|
| **L0** | `mail/adapters/_shared/agent-universal/` | 全 agent 红线、ack、phantom 禁止、团队规则指针 |
| **L0** | `mail/adapters/_shared/mailbus-file-protocol/` | mailbus 路由、push 纪律 |
| **L1** | `mail/adapters/{framework}/framework-runtime/` | push CLI、auto_ack、交付 SoT、workspace 约定 |
| **L2** | `mail/roles/archetypes/{name}/` | 工种边界、SPARC 段、交付物格式 |
| **L2** | `mail/roles/overlays/{agent}/` | agent 专属 skill 列表、阶段门禁 |
| **L3** | 各 domain skill | TDD、tarot、patroller SOP 等 |

## Spec 包结构（统一）

```
{package}/
├── SPEC.md
├── boundaries.md
├── conventions.md
├── checklist.md
├── SKILL.md          # ≤120 行
└── references/
```

## skills-index 顺序

1. `agent-universal` (L0)
2. `mailbus-file-protocol` (L0)
3. `framework-runtime-{framework}` (L1)
4. `role-{archetype}` (L2)
5. `role-overlay-{agent}` (L2)
6. domain skills (L3)

补全：`python mail/tools/patch-skills-index-framework.py`  
校验：`python mail/tools/validate-agent-layers.py --check`  
一键 sync：`python mail/tools/sync-all-agent-layers.py`  
（含 Hermes profile → `mail/adapters/.sync/{agent}/skills`；容器 entrypoint 也会自动 sync）

## identity vs role

- **`mail/identities/`** — 人设、职责摘要、装备 skill 表；**不含** mailbus inline 交付规则
- **`mail/roles/`** — 工种 spec 边界（机器可组合）

## 编码与 mattpocock/skills

SPARC ↔ Matt 映射 → `mail/roles/archetypes/_shared/mattpocock-bridge.md`
