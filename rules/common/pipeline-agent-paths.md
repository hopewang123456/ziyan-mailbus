# Pipeline Agent 路径规范（mailbus 侧）

> **所有 agent 在执行 pipeline 任务时，必须使用以下路径写入文件。**
> mailbus 已为各 agent 容器挂载 `/mailbus/store`（读写）与 `/mailbus/rules`（只读）。
> **禁止**使用 `/mnt/e/...`（容器内不可达）或容器内临时沙箱路径。

## 统一根路径

| 用途 | 路径 |
|------|------|
| 数据根 | `/mailbus/store` |
| 规则 | `/mailbus/store/rules/` 或 `/mailbus/rules/` |
| inbox | `/mailbus/store/inbox/<agent>/inbox.json` |
| ack | `/mailbus/store/inbox/<agent>/ack.json` |
| pipeline 结果 | `/mailbus/store/msg-results/<task_id>.json` |
| 交付物 | `/mailbus/store/deliverables/<task_id>/` |
| 步骤工单 | `/mailbus/store/msg-files/<msg_id>.md` |

## msg-results 必填字段（pipeline 步骤）

```json
{
  "task_id": "game-stellar-YYYYMMDD",
  "agent": "<当前 agent id>",
  "pipeline_step": 1,
  "conclusion": "done",
  "summary": "<本步结论>",
  "timestamp": "2026-06-17T12:00:00+08:00"
}
```

**无此文件 = 本步未完成**，mailbus 不会推进下一步。stdout 回复、`replies/*.json` 均不算完成。

## ack 格式

```json
{"action": "ack", "msg_id": "<消息ID>", "agent": "<agent>", "timestamp": "<ISO8601>"}
```

写入 `/mailbus/store/inbox/<agent>/ack.json`（覆盖写入单条 JSON 或数组追加，以 scanner 能读到为准）。

## 工单流转字段（inbox 消息 / msg-files）

执行 pipeline 任务时，inbox 消息会带 `task_id` 字段；`msg-files/*.md` 工单含：

- **发起人**：mailbus / 上一步 agent
- **当前执行人**：inbox 消息的 `to`
- **下一步执行人**：`planned_agents[0]`（见 task tracker）
- **任务 ID**：`task_id`
- **状态**：inbox `state` + tracker `chain[-1].status`
- **summary**：上一步 `msg-results.summary` 或任务描述

## 验证挂载

```bash
bash docker-agents/verify-agent-store-mount.sh
```
