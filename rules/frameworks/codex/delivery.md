# Codex — 交付

## 强制 msg-results

路径：`store/msg-results/{msg_id}.json`

```json
{
  "agent": "lingxiao",
  "msg_id": "<id>",
  "status": "done",
  "summary": "≤200字：做了什么、测了什么",
  "checklist": ["约束1✓"],
  "timestamp": "<ISO8601>"
}
```

## 与 mailbus

- `mark_processing_on_task_push: true`：push 后 task 变 running，等 msg-results
- 禁止 phantom 回执（只写 inbox 聊天不写 results）

## patch 可选

Codex 路径以 msg-results 为主；若工单要求 PR/patch，在 summary 注明路径。
