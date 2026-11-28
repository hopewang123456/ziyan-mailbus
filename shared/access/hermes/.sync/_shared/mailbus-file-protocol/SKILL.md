---
name: mailbus-file-protocol
description: >
  mailbus 文件任务协议（全框架共用）。收到 mailbus 消息时必读。
  路由：交付 checkpoint → references/ack-and-results.md；
  省 token 推送纪律 → references/push-discipline.md。
always: true
type: shared_skill
---

# mailbus 文件协议 — 路由器

所有 agent 框架共用。框架特有 push/交付差异见各 `framework-runtime-*` skill。

## 收到消息后（必做）

1. 写 ack → `store/inbox/{agent}/ack.json`
2. 若有 `store/msg-files/{msg_id}.md` → **先完整阅读**再执行
3. 完成后写交付 SoT（见下表），禁止空泛「已完成」

## 交付 SoT 速查

| 框架类型 | 完成必须 |
|----------|----------|
| codex / claude_code / cline | `store/msg-results/{msg_id}.json` |
| opencode (dali) | git patch + `store/replies/{sender}.json` |
| hermes / openclaw | 实质回复或约定文件；notice 可 auto_ack |
| cursor（设计） | 规划为 msg-results，**当前未实现** |

详细格式 → [references/ack-and-results.md](references/ack-and-results.md)

## 省 token（推送侧）

- CLI 正文 ≤600 字；长文放 `store/tasks/`、`msg-files/`、`msg-results/details`
- task 推送只含 **msg_id + 文件路径**
- 编码重活走 **Cursor 直连**，mailbus 只管流转

详细 → [references/push-discipline.md](references/push-discipline.md)

## msg-results 最小 schema

```json
{
  "agent": "<agent_id>",
  "msg_id": "<msg_id>",
  "status": "done|failed",
  "summary": "≤200字",
  "checklist": ["约束1✓"],
  "timestamp": "<ISO8601>"
}
```

## 自检 checkpoint

- [ ] 已写 ack
- [ ] 已读 msg-files（若存在）
- [ ] 已写对应 SoT（msg-results / patch+replies / 实质回复）
- [ ] summary ≤200 字
