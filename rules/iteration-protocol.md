# Agent 迭代协议（Iteration Protocol）

> **硬规则：Round1 执行 success + 灵鉴 audit 通过 → 才允许 Round2。**  
> scan 每轮只刷新 Round1 诊断，**不会**自动生成 Round2 工单。

## 审计与「待审计」

Dashboard「待审计」= **根 pipeline 任务**终态且无 `audit_log`。

- `msg-*` 投递 tracker、`game-lvup-*` 回归：**不要求**侧链审计（`requires_audit=false`）
- pipeline **审查官步骤**完成 → 自动写入 `audit_log`（与 chain 一体，非侧链）
- Round1 主任务未经审查官 → scan 派 `audit-req-*` 给灵鉴（每轮最多 2 条）
- 灵鉴也可 `POST /api/tasks/audit` 或写 `audit-{task_id}.json`

**仅 ACK 不算审计完成。**

## 三轮模型（修正版）

```
Round 1 执行+审计     Round 2  stabilization      Round 3 自迭代
(主任务 success      (仅 gate 通过后)            (R2 全完成)
 + 灵鉴 audit pass)
        ↓
 round-1-gate.json → round2_unlocked=true → 才生成 round-2-backlog.json
```

## 门禁文件

| 文件 | 含义 |
|------|------|
| `iteration-state.json` | 当前阶段、主任务 ID |
| `round-1-gate.json` | **blockers[]** / **round2_unlocked** |
| `round-1-diagnosis.json` | 现象与问题（scan 自动刷新） |
| `round-2-backlog.json` | 未解锁时 status=blocked |

## Round1 完成标准（解锁 Round2）

1. 主任务 `iteration-state.primary_task_id`（当前见 `iteration-state.json`）→ **status=success**
2. 同任务 **audit_log** 存在且 **result ∈ {pass, warn}**

查看：`cat store/iterations/round-1-gate.json`

## Agent 职责

### 灵昭 — Round1 执行
- 推进 hardening pipeline，写 `msg-results/mailbus-hardening-20260616.json`
- **不要** 在 gate 未通过时触发 Round2

### 灵鉴 — Round1 审计（关键）
- 处理 inbox 中 `audit-req-*` 消息
- 提交审计：
```bash
curl -X POST http://127.0.0.1:9814/api/tasks/audit \
  -H 'Content-Type: application/json' \
  -d '{"task_id":"mailbus-hardening-20260616","reviewer":"lingjian","result":"pass","summary":"..."}'
```
或写 `store/msg-results/audit-mailbus-hardening-20260616.json`：
```json
{"audit":true,"task_id":"mailbus-hardening-20260616","agent":"lingjian","result":"pass","summary":"..."}
```

### 小七 — Round2 调度（仅 gate 通过后）
- `bus iteration --round 2` 返回 0 后才派 Round2 工单

## CLI

```bash
python3 -m bus iteration --round 1 --data-dir store   # 默认，仅诊断+门禁
python3 -m bus iteration --round 2 --data-dir store   # gate 未过则 exit 1
python3 -m bus iteration --round all --data-dir store # 未解锁则不全量生成 R2

bash docker-agents/run-mailbus-iteration.sh 1 dispatch-r1  # 只下发 Round1
```

## 禁止

- ❌ Round1 未完成就 `bus iteration --round 2` 或 `dispatch-r2`
- ❌ 灵鉴只 ACK 不写 audit_log
- ❌ 把 timeout 任务当 Round1 成功（须先 success 或修复后重跑 pipeline）
- ❌ 提交 `.env.secrets` / API Key 到 git（见 `team-secrets-policy.md`）

## 执行顺序与并发

详见 **`store/rules/execution-order.md`**：

- 每 agent **串行**推送（同时仅 1 条 pushed/processing 任务）
- **主任务** `iteration-state.primary_task_id` 优先于 Round2
- 编排器 **light 模式**：仅去重 Round2 重复，**不 cancel 主 pipeline**
- 监控：`python3 tools/pipeline-watchdog.py --data-dir store`

## 团队规范同步

```bash
python3 tools/sync-team-rules.py --data-dir store
```

同步到：公告板 + AgentMemory（全员）+ 各 agent inbox notice。  
密钥规范：`store/rules/team-secrets-policy.md`

## 自愈（无需手动脚本）

每轮 `bus scan`（cron 每分钟）自动执行 `lib/self_heal.py`：

| 能力 | 说明 |
|------|------|
| reply → msg-results | agent 写了 inbox/mailbus 回复但未写 msg-results 时自动回收 |
| tracker/inbox 对齐 | 有 msg-results 或任务终态时自动关闭 processing 僵尸 |
| 无 CLI 释放 | ACK 后 Hermes/Cline/OpenClaw 已退出 → 2 分钟内重置 pending 重推 |
| 历史审计归档 | 测试/催办/过期任务自动 warn 审计，不再堆积「待审计」 |

**不要**再依赖 `tools/followup-tasks.py` 手工推进；排查用 `tools/triage-tasks.py` 只读盘点即可。
