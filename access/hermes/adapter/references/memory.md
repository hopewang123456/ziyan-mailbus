# Hermes — 记忆

> 分流 SoT：mailbus 规则 `01-mailbus/011-rule/0111-common/memory-routing.md`（勿在 identity 另写）。

## 开工前

```bash
python3 "$HERMES_HOME/scripts/memory.py" search "<decision|checklist|关键词>"
python3 "$HERMES_HOME/scripts/cost.py" report   # 预算（若脚本存在）
```

## 路径

- 宿主 `HERMES_DATA`：在 `docker-agents/.env` 或设置页显式填写；未设时 compose 回落 `docker-agents/workspaces/hermes-data`
- `HERMES_HOME`：容器内 `/home/hermes/.hermes`（由上目录挂载）
- 团队 SQLite：`shared-memory/team-memory.db`（经 mailbus memory_bridge）
- MemOS 运行时：`$HERMES_HOME/memos-plugin/`（个人层；迁移时随 `HERMES_DATA` 整目录带走）

## 写入

| 内容 | 落点 |
|------|------|
| 工单回复、任务流程、决策、checklist | **AgentMemory**（`AGENTMEMORY_URL` / MCP `agentmemory` / `memory.py`） |
| 偏好、习惯、个人会话经验 | **MemOS**（`memory.provider: memtensor`） |
| 极短硬约束 | 内置 `MEMORY.md` / `USER.md` |

- 重要决策写入 AM，勿只靠 chat 历史或 MemOS
- 同一事实禁止 AM + MemOS 双写无主

## 省 token

- search 用精确关键词，不要 `search "everything"`
- 限制条数（memory_bridge_limit 默认 5）
