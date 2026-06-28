# Mailbus HTTP API — Phase 4 变更摘要

> Base URL 默认 `http://127.0.0.1:9814`（`MAILBUS_API_PORT` / `config/mailbus.json`）。  
> Docker compose 与原生 serve 均已统一 **9814**（2026-06-26）。

## Breaking / 新增端点

### Task FSM

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tasks/<task_id>/fsm/continue` | 同 step 重 push（`recover_continue`） |
| POST | `/api/tasks/<task_id>/fsm/cancel` | 取消并释放 task lock |
| POST | `/api/tasks/<task_id>/fsm/rollback` | 回退；body: `reason`, `to_step?`, `to_agent?` |
| POST | `/api/tasks/<task_id>/fsm/priority` | 调整 FSM 优先级；body: `priority`（数值越小越加急） |
| POST | `/api/tasks/<task_id>/fsm/pause` | 暂停 |
| POST | `/api/tasks/<task_id>/fsm/approve-plan` | 计划审批 |
| POST | `/api/tasks/<task_id>/fsm/accept` | 终验 accept/deny |

### Human queue（统一 resolve）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/human-queue?status=pending` | 待办列表 |
| POST | `/api/human-queue/<hq_id>/resolve` | **推荐** 统一审批入口；body: `decision`, `reviewer`, `comment`, `reason`, `brief?`, `attachments?` |

`resolve` 按 item `type` 自动路由：

- `plan_approval` → `apply_approve_plan`
- `final_acceptance` → `apply_accept`
- `intake_gate` → intake gate approve/deny
- `workflow_gate` / 带 `task_id+gate_id` → `on_gate_approve` / `on_gate_deny`

### Workflow gates（仍可用，resolve 为 Dashboard 首选）

| POST | `/api/tasks/<id>/gates/<gate_id>/approve` |
| POST | `/api/tasks/<id>/gates/<gate_id>/deny` |

### 已废弃 / 410

- Legacy chain-array task create → 见 `store/rules/a2a-task-create-api.md`
- 硬编码 `/mnt/e/ai_tools/mail/store` 路径 → 使用 `MAILBUS_DATA`

## CLI 等价

```bash
python mail/bus.py recover continue --task-id <id> --data-dir store
```

## 告警类型（alerter）

新增 `interrupted`：scan 检测到 pipeline assignee CLI 无响应时推送灵昭/小七 inbox。

## 环境变量

见 `mail/config/env.template`：`MAILBUS_ROOT`, `MAILBUS_DATA`, `MAILBUS_API_PORT`.
