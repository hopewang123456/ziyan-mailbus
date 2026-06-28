---
name: role-overlay-lingjian
description: >
  L2 lingjian 专属 overlay。extends code-reviewer。
always: true
type: role_overlay
layer: L2
extends: code-reviewer
agent_id: lingjian
---

# Role Overlay — lingjian

> **extends**: `role-code-reviewer` · **identity**: `mail/identities/lingjian.md`

## SPARC 门禁

[R:review] 审查报告

## 听命链

见 identity 文件。

## 装备 skill（L3 按需）

见 `roles-skills-map.md` 与 `store/agents/json/skills-index.json`。

## 开工前（编码类）

1. memory search decision/checklist
2. cost report（如适用）
3. 加载 L3 domain skills（工单指定）
