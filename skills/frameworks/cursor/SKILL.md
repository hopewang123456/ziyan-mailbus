---
name: framework-runtime-cursor
description: >
  Cursor SDK 框架边界（NOT IMPLEMENTED 设计 stub）。编码走 Cursor 直连，mailbus 只流转。
always: true
type: framework_skill
layer: L1
framework: cursor
status: not-implemented
---

# Cursor Framework Runtime（设计 stub）

> **status: not-implemented** — `CursorAdapter` 未注册；见 `mail/docs/cursor-adapter-design.md`  
> **勿调用** `Agent.prompt` / Cursor SDK API，除非 adapter 已上线。

## 规划 Push 形态

```
Agent.prompt(task) → headless → msg-results
```

- 无 auto_ack（规划与 codex/claude_code 一致）
- 完成 SoT：`store/msg-results/{msg_id}.json`

## 当前实际分工

| 工作 | 路径 |
|------|------|
| 重编码 / refactor | **Cursor IDE 直连**（用户会话） |
| 跨 agent 流转 | mailbus push 到其他 framework |
| Token 策略 | model-routing：mailbus 不烧 token 做编码 |

## 若未来实现

1. 读 cursor-adapter-design.md
2. ack + msg-files + msg-results
3. permission 与 workspace root 由 config 注入

## 参考

- 设计 doc：[`../../../docs/cursor-adapter-design.md`](../../../docs/cursor-adapter-design.md)
- 交付（规划）→ [`../codex/references/delivery.md`](../codex/references/delivery.md)

## 自检（设计）

- [ ] 确认 adapter 是否已实现（当前：**否**）
- [ ] 未实现时勿假装已走 Cursor SDK push
