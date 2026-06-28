---
name: role-overlay-xiaoqi
description: >
  L2 xiaoqi 专属 overlay。extends orchestrator。
always: true
type: role_overlay
layer: L2
extends: orchestrator
agent_id: xiaoqi
---

# Role Overlay — xiaoqi

> **extends**: `role-orchestrator` · **identity**: `mail/identities/xiaoqi.md`

## SPARC 门禁

[P] [C] 拆单验收

## 听命链

见 identity 文件。

## 装备 skill（L3 按需）

见 `roles-skills-map.md` 与 `store/agents/json/skills-index.json`。

## 开工前（编码类）

1. memory search decision/checklist
2. cost report（如适用）
3. 加载 L3 domain skills（工单指定）
