# Runbook — 断链恢复 / 取消 / 驳回 / 回退

## 继续（同 step 重 push）

**CLI**

```bash
python mail/bus.py recover continue --task-id <task_id> --data-dir store
```

**Dashboard API**

```http
POST /api/tasks/<task_id>/fsm/continue
Content-Type: application/json

{"reason": "operator_continue"}
```

实现：`lib/task_recover.recover_continue` · task lock 由 recover 持有，push 路径可重入。

**值班场景**：scan 日志出现 `interrupted` / alerter 推送后，先确认 agent 进程是否存活（Dashboard 系统页或 `docker compose ps`）。若 CLI 已退出，重启 agent 后再点「继续」；若 inbox 已有 stale processing，recover 会同 step 重 push work-order。

## 取消

```http
POST /api/tasks/<task_id>/fsm/cancel
{"reason": "..."}
```

释放 `store/locks/task-{task_id}.json`（若存在）。

**值班场景**：用户明确要求放弃任务、或重复派单需 supersede 时取消。取消后 inbox 中 processing 消息会被 supersede；**不可**用 cancel 代替 rollback（审查不合格应走回退）。

## 驳回 / 回退

```http
POST /api/tasks/<task_id>/fsm/rollback
{"reason": "...", "to_step": 2, "to_agent": "lingzhao"}
```

与 workflow gate `deny` / `rollback_phase` 共用 `apply_rollback`。

**值班场景（审查/设计不合格）**：

1. 灵鉴/灵昭 msg-results 写 `conclusion: failed` 且 `action: rollback`，或 Dashboard 点「回退」。
2. 填写 **rejection_reason**、**return_to_step** / **return_to_role**（若 API 支持）。
3. FSM 调用 `apply_rollback` 追加 redo step，保留历史 chain；新 work-order 的 Context 须含驳回意见。
4. 若 human_queue 有 pending gate，可用 `POST /api/human-queue/<id>/resolve` 传 `decision: denied` 触发同等回退路径。

**勿混淆**：rollback = 退回上游重做；cancel = 终止整条 task；continue = 同 step 重试（断链/ push 失败）。

## 人工待办

```http
GET  /api/human-queue?status=pending
POST /api/human-queue/<hq-id>/resolve
{"decision": "approved|denied", "comment": "..."}
```

SoT：`store/human-queue.json`

**值班场景**：workflow gate 需人工审批（如方案确认、发布许可）。`approved` 推进 FSM；`denied` 等价驳回并应附 comment 供下游 work-order 引用。

## 快速诊断

| 现象 | 检查 | 动作 |
|------|------|------|
| task 卡 processing 无 msg-results | `store/locks/task-*.json`、inbox state | continue 或 cancel |
| OpenCode phantom done | `store/patches/`、`replies/` 无 msg-results | Normalizer + `docs/runbook-phantom-opencode.md` |
| 同 step 失败 ≥2 次 | pipeline failover 日志 | 等待同工种改派或 Dashboard blocked |
| scheduler 无 scan | `store/logs/scheduler.log` | 确认 `bus serve` / Docker mailbus 运行 |

