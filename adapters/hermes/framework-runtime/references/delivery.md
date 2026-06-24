# Hermes — 交付

## task

1. ack → `store/inbox/{agent}/ack.json`
2. 读 `msg-files` / `tasks`
3. 输出：chat 回复 + 可选 `store/msg-results/{id}.json` 或 deliverables

## notice

- adapter `supports_auto_ack: true`
- 仍应简短确认，避免无意义长回复

## msg-results（推荐）

与 codex 同 schema，便于小七验收：

```json
{"agent":"lingzhao","msg_id":"...","status":"done","summary":"≤200字","timestamp":"..."}
```

## patch 流程

Hermes 角色通常 **不** 走 dali 式 git patch；编码交付派给 dali/lingyun。
