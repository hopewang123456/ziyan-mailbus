# mailbus 执行顺序与并发规范

> 避免多任务竞争导致 mailbus 阻塞或 agent 卡死  
> 实现：`lib/scanner.py` + `lib/execution_orchestrator.py` + `config.scheduler`

## 设计原则

**不是多 agent 并行抢 mailbus**，而是：

1. **每 agent 串行** — 同一 agent inbox 同时最多 1 条 `pushed/processing` 可执行任务（P2 约束）
2. **主任务优先** — `iteration-state.json` 的 `primary_task_id` pipeline 插队 urgent 队列
3. **Round 门禁** — Round1 未 success + audit 前，Round2 仅 `pending` 降权，不推送
4. **调度互斥** — scheduler job 用 `/tmp/mailbus-*.lock` flock，避免 scan/bridge 重叠
5. **HTTP 多线程 ≠ 推送多线程** — API 用 ThreadingMixIn，scan 单线程 + flock

## 推送优先级（单 agent 内）

```
tier 0  running pipeline 任务（含 primary_task_id）
tier 1  可执行 task（非 Round2 或 gate 已开）
tier 8  Round2 工单（gate 未开时降权）
tier 9  inbox_overflow / 催办 notice（pipeline 运行中自动 done）
```

## 编排器（`execution_orchestrator` mode=light）

| 动作 | 条件 |
|------|------|
| cancel 重复 Round2 tracker | 同 agent 多条 Round2 **且** gate 未开 → 只留最新 |
| **不** cancel 主任务 | `primary_task_id` 及关联 inbox 永不 cancel |
| reset Round2 inbox | 重复 Round2 消息 → `pending`（非 done），gate 通过后重推 |
| 检测异常 | 无 CLI 的 processing、duplicate running、主任务 stalled |

**禁止**使用旧版 aggressive 全量 cancel（已移除）。

## 自愈（每轮 scan 前）

- `agent_cli_active()` — 无 Hermes/Cline/OpenClaw 进程 → 2min 释放 processing
- `recover_inbox_stale_states()` — pushed 超时、notice 快速 done
- `run_orchestrator(mode=light)` — 保守去重

## 监控

```bash
python3 mail/tools/pipeline-watchdog.py --data-dir mail/store
python3 mail/tools/ops/tools/ops/triage-tasks.py
```

scheduler 每 5 分钟自动跑 `pipeline_watchdog` job。

## Agent 协同流程（当前）

```
Round1: 主任务 pipeline（灵昭→…→灵鉴 audit）→ round-1-gate 解锁
Round2: dispatch-r2（仅 gate 后）→ 各 owner 写 iteration-r2-*.json
Round3: backlog 全 done → protocol 更新
```

### 各角色要点

| Agent | 当前阶段动作 |
|-------|----------------|
| 灵昭 | 写 `msg-results/{primary_task_id}.json`，推进 pipeline |
| 灵拓 | 更新 `order-intake.json`；pursue/高分通知灵昭或一哥 |
| 灵账 | 验收后维护 `billing/accounts.json`；账期提醒 |
| 灵鉴 | 处理 audit-req，POST `/api/tasks/audit` |
| 小七 | gate 通过后再调度 Round2 |
| 灵霄/灵验/灵鉴 | Round2 工单 gate 后再执行 |

## 已知限制 / 待办

- [ ] inbox 历史积压（如 xiaoqi 500+）需专门 archive 工单，不影响主 pipeline
- [ ] `msg-*` tracker 与主任务 inbox 可能重复 — 以 `primary_task_id` tracker 为准
- [ ] 17 条历史 `cancelled` Round2 重复 dispatch — 可保留，无需恢复
