---
name: mailbus-file-protocol
description: >
  L0 mailbus 文件协议路由。ack、读 msg-files、push 纪律。交付 SoT 见 L1 framework-runtime。
always: true
type: shared_skill
layer: L0
---

# mailbus 文件协议 — 路由器（L0）

与 `agent-universal` 组合加载。框架 push/交付 → 各 `framework-runtime-*` skill。

## 收到消息后（必做）

1. 写 ack → `store/inbox/{agent}/ack.json`
2. 若有 `store/msg-files/{msg_id}.md` → **先完整阅读**再执行
3. 完成后写 **L1 交付 SoT** → `framework-runtime-*/references/delivery.md`
4. 禁止空泛「已完成」

## 交付 SoT

**不在此定义。** 各框架 exclusive → L1 `references/delivery.md`。

## 省 token（推送侧）

- CLI 正文 ≤600 字；长文放 `store/tasks/`、`msg-files/`
- task 推送只含 **msg_id + 文件路径**

详细 → [references/push-discipline.md](references/push-discipline.md)

## 按需 Read

| 主题 | 文件 |
|------|------|
| ack 格式 | [references/ack-and-results.md](references/ack-and-results.md) |
| L0 通用边界 | [../agent-universal/SKILL.md](../agent-universal/SKILL.md) |
| push 纪律 | [references/push-discipline.md](references/push-discipline.md) |

## 自检

- [ ] 已写 ack
- [ ] 已读 msg-files（若存在）
- [ ] 已写 L1 交付 SoT
- [ ] summary ≤200 字
