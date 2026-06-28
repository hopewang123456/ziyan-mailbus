---
name: agent-universal
description: >
  L0 全 agent 通用边界。红线、mailbus ack/读工单、phantom 完成禁止、团队规则指针。
  交付 SoT 见 L1 framework-runtime；工种见 L2 role-*。
always: true
type: shared_skill
layer: L0
---

# Agent Universal（L0）

所有子言·AI 团队 agent **必须**遵守。与 `mailbus-file-protocol` 组合加载。

## 必做（收到 mailbus 消息）

1. ack → `store/inbox/{agent}/ack.json`
2. 读 `store/msg-files/{msg_id}.md`（若存在）
3. 完成后写 **L1 交付 SoT** — 见 `framework-runtime-*/references/delivery.md`
4. 禁止空泛「已完成」

## 红线

- 不外泄私有数据/密钥
- 不擅自 destructive 操作
- 不越权做其他工种工作（L2 boundaries）
- summary ≤200 字

## 按需 Read

| 主题 | 文件 |
|------|------|
| 完整 spec | [SPEC.md](SPEC.md) |
| 边界 | [boundaries.md](boundaries.md) |
| 规范 | [conventions.md](conventions.md) |
| 自检 | [checklist.md](checklist.md) |
| 团队规则 | [references/team-rules.md](references/team-rules.md) |
| mailbus 核心 | [references/mailbus-core.md](references/mailbus-core.md) |

## 分层

```
L0 本 skill + mailbus-file-protocol
L1 framework-runtime-{framework}
L2 role-{archetype} + role-overlay-{agent}
L3 domain skills（按需）
```

Meta → `mail/docs/agent-layer-spec.md`
