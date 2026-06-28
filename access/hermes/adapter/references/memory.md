# Hermes — 记忆

## 开工前

```bash
python3 "$HERMES_HOME/scripts/memory.py" search "<decision|checklist|关键词>"
python3 "$HERMES_HOME/scripts/cost.py" report   # 预算（若脚本存在）
```

## 路径

- `HERMES_HOME`：容器内 `/home/hermes/.hermes`
- 团队 SQLite：`shared-memory/team-memory.db`（经 mailbus memory_bridge）

## 写入

- 重要决策写入 memory（按团队规范），勿只靠 chat 历史
- AgentMemory：`AGENTMEMORY_URL`（iii-engine:3111）

## 省 token

- search 用精确关键词，不要 `search "everything"`
- 限制条数（memory_bridge_limit 默认 5）
