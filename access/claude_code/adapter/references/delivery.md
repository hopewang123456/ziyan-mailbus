# Claude Code — 交付

## msg-results（强制）

```json
{
  "agent": "lingyun",
  "msg_id": "<id>",
  "status": "done",
  "summary": "≤200字",
  "checklist": ["约束1✓"],
  "timestamp": "<ISO8601>"
}
```

## sync 链路

```bash
python mail/tools/sync-claude-agent-context.py lingyun
```

刷新：`CLAUDE.md`、skills、`{agent}-memory/output.md`

## 失败

`status: failed` + `reason` 字段，便于小七重派
