# Claude Code — Token

- `CLAUDE.md` 截断 identity ≤12000 字（sync 侧）
- memory skill：`{agent}-memory/output.md` 快照，勿重复拉 AgentMemory
- 长工单只在 msg-files；`-p` 正文短
- 跨文件 refactor：先 Glob 再 Read 必要文件，避免全库 read
- max_concurrency: 1 — 串行任务，结果及时写 msg-results 释放调度
