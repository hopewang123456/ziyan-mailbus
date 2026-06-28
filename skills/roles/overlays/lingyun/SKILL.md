---
name: role-overlay-lingyun
description: >
  L2 lingyun 专属 overlay。extends coding-pro。
always: true
type: role_overlay
layer: L2
extends: coding-pro
agent_id: lingyun
---

# Role Overlay — lingyun

> **extends**: `role-coding-pro` · **identity**: `mail/identities/lingyun.md`

## SPARC 门禁

[A→R] pro 长工单

## 听命链

见 identity 文件。

## 装备 skill（L3 按需）

见 `roles-skills-map.md` 与 `store/agents/json/skills-index.json`。

## Matt skills（pro 编码）

| 场景 | Skill |
|------|-------|
| 长工单开工 | `/grill-with-docs` |
| 实现/refactor | `/tdd` |
| 架构熵 | `/improve-codebase-architecture` |

→ `mail/roles/archetypes/coding-pro/references/matt-skills.md`

## 开工前（编码类）

1. memory search decision/checklist
2. cost report（如适用）
3. 加载 L3 domain skills（工单指定）
