---
name: role-overlay-dali
description: >
  L2 dali 专属 overlay。extends coding-executor。
always: true
type: role_overlay
layer: L2
extends: coding-executor
agent_id: dali
---

# Role Overlay — dali

> **extends**: `role-coding-executor` · **identity**: `mail/identities/dali.md`

## SPARC 门禁

[P→A] [A→R] [R:review]

## 听命链

见 identity 文件。

## 装备 skill（L3 按需）

见 `roles-skills-map.md` 与 `store/agents/json/skills-index.json`。

## Matt skills（编码）

| 场景 | Skill |
|------|-------|
| 开工 | `/grill-with-docs` |
| 实现 | `/tdd` |
| 调试 | `/diagnose` |

→ `mail/roles/archetypes/coding-executor/references/matt-skills.md`

## 开工前（编码类）

1. memory search decision/checklist
2. cost report（如适用）
3. 加载 L3 domain skills（工单指定）
