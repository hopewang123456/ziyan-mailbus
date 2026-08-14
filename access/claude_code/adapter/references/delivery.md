# Claude Code — 交付

## msg-results（强制）

```json
{
  "agent": "agent-h",
  "msg_id": "<id>",
  "status": "done",
  "summary": "≤200字",
  "checklist": ["约束1✓"],
  "timestamp": "<ISO8601>"
}
```

## sync 链路

```bash
python mail/tools/sync-claude-agent-context.py agent-h
```

刷新：`CLAUDE.md`、skills、`{agent}-memory/output.md`

## 失败

`status: failed` + `reason` 字段，便于调度员重派
