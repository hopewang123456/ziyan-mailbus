# 闭环任务方案设计规范

> 灵昭必读 · 与 skill `closed-loop-task-design` 同步 · 2026-06-16

## 问题背景

以往任务常见问题：
1. chain 只有 6 人，声称全流程却漏 4 人
2. 灵霄/大力同角色，pipeline 重复派灵霄
3. msg-results 缺 `pipeline_step` / `agent`，链卡住
4. 方案无验收标准，灵验/小七无法闭环

## 标准 12 步 chain（全员验收模板）

```
lingzhao → lingxi → lingzhao → xiaoqi → lingxiao → dali
→ lingjin → lingjian → lingyan → lingxun → yige → xiaoqi
```

创建后 `chain[0].planned_agents` 自动填充；pipeline 按序弹出，**不需要**每步手写 `next_person`（除非 override）。

## planned_agents 机制（2026-06-17 修订）

| 规则 | 说明 |
|------|------|
| **planned 优先** | 队列非空时 **始终 pop**，忽略 result.next_role 跳步 |
| **串台拒绝** | 拒绝 `auto-linked-from-*` / `auto-recovered-from-*` |
| **agent 严格** | result.agent 必须等于当前 step 的 to_person |
| **禁止假 success** | planned 未清空或非验收员 approved 不得终态 |

实现：`lib/pipeline_routing.py` + `lib/pipeline_trigger.py`

## 当前验收任务

- **task_id**: `game-stellar-20260617`（v2，**status=success** 2026-06-17）
- **游戏**: 《星际驿站 Stellar Mail Hub》终端 MVP — `deliverables/game-stellar-20260617/`
- **目的**: mailbus 12 agent 通信 + 异构 CLI 压测

## 商前/商后（非 12 步 pipeline 内）

- **灵拓** `lingtuo`：商机 intake，经 mailbus 通知衔接灵昭
- **灵账** `lingzhang`：验收 approved 后账期/回款，独立商后链
- **排查 playbook**: `pipeline-debug-playbook` skill（灵昭必读）
