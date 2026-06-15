# 任务链类型定义

> 每条任务从发起到完成，经过的节点序列。
> 每个节点 = {from, to, action, report, status, timestamps}
> 灵巡通过检查 chain[-1] 就知道当前该谁干活。

---

## 链类型 A：完整开发链（新功能/大重构）

```
灵昭 → 小七(调度) → 大力/灵霄(开发) → 灵鉴(审查) → 灵验(测试) → 小七(验收) → 完成
```

| 步骤 | from | to | action | 产出报告 | 说明 |
|------|------|----|--------|----------|------|
| 1 | 灵昭 | 小七 | 派发 | dispatch-report | 灵昭出方案，派给小七调度 |
| 2 | 小七 | 大力/灵霄 | 调度开发 | dispatch-report | 小七拆任务派给开发 |
| 3 | 大力/灵霄 | 灵鉴 | 开发完成 | dev-report | 开发完成，自测通过 |
| 4 | 灵鉴 | 灵验 | 审查 | review-report | 审查通过→给测试，不通过→退回开发 |
| 5 | 灵验 | 小七 | 测试 | test-report | 测试通过→给验收，不通过→退回开发 |
| 6 | 小七 | (完成) | 验收 | approve-report | 验收通过=任务完成 |

---

## 链类型 B：轻量开发链（小改动/配置/文档）

```
灵昭 → 大力/灵霄(改) → 灵鉴(审查) → 小七(验收兼测) → 完成
```

| 步骤 | from | to | action | 产出报告 |
|------|------|----|--------|----------|
| 1 | 灵昭 | 大力/灵霄 | 派发(小任务) | dispatch-report |
| 2 | 大力/灵霄 | 灵鉴 | 修改完成 | dev-report |
| 3 | 灵鉴 | 小七 | 审查 | review-report |
| 4 | 小七 | (完成) | 验收兼测试 | approve-report(含测试结果) |

---

## 链类型 C：纯审查链（安全审计/架构评审/代码走读）

```
灵昭 → 灵鉴(审查) → 灵验(测试) → 小七(验收) → 完成
```

| 步骤 | from | to | action | 产出报告 |
|------|------|----|--------|----------|
| 1 | 灵昭 | 灵鉴 | 发起审查 | dispatch-report |
| 2 | 灵鉴 | 灵验 | 审查 | review-report |
| 3 | 灵验 | 小七 | 测试 | test-report |
| 4 | 小七 | (完成) | 验收 | approve-report |

---

## 链类型 D：紧急修复链（P0故障/线上问题）

```
灵昭 → 大力/灵霄(热修) → 灵验(测试) → 小七(验收) → 完成
```

| 步骤 | from | to | action | 产出报告 |
|------|------|----|--------|----------|
| 1 | 灵昭 | 大力/灵霄 | 紧急派发 | dispatch-report |
| 2 | 大力/灵霄 | 灵验 | 热修完成 | dev-report(标记 urgent) |
| 3 | 灵验 | 小七 | 测试(快速) | test-report |
| 4 | 小七 | (完成) | 验收上线 | approve-report |

> 注意：紧急修复跳过审查环节，但测试不能省。

---

## 链类型 E：调研链（技术调研/方案选型）

```
灵昭 → 灵犀(调研) → 灵昭(决策) → 小七(执行/存档) → 完成
```

| 步骤 | from | to | action | 产出报告 |
|------|------|----|--------|----------|
| 1 | 灵昭 | 灵犀 | 发起调研 | dispatch-report |
| 2 | 灵犀 | 灵昭 | 调研完成 | research-report |
| 3 | 灵昭 | 小七 | 决策 | decision-report（或存档）|
| 4 | 小七 | (完成) | 执行/归档 | task-report |

---

## 链类型 F：巡检链（灵巡日常巡检）

```
mailbus → 灵巡(巡检) → (存档)
```

| 步骤 | from | to | action | 产出报告 |
|------|------|----|--------|----------|
| 1 | mailbus | 灵巡 | 定时巡检 | — |
| 2 | 灵巡 | (存档) | 巡检 | patrol-report |

> 巡检链不涉及派发，灵巡完成报告后自动存档。

---

## 链类型 G：运营链（一哥日常运营）

```
灵昭/小七 → 一哥(执行) → 灵昭/小七(确认) → 完成
```

| 步骤 | from | to | action | 产出报告 |
|------|------|----|--------|----------|
| 1 | 灵昭/小七 | 一哥 | 派发运营任务 | dispatch-report |
| 2 | 一哥 | 灵昭/小七 | 执行完成 | task-report |
| 3 | 灵昭/小七 | (完成) | 确认 | confirm-report |

---

## 链类型 H：安全审计链（灵瑾安全审查）

```
灵昭/灵鉴 → 灵瑾(审计) → 大力/灵霄(修复) → 灵瑾(复审) → 小七(验收) → 完成
```

| 步骤 | from | to | action | 产出报告 |
|------|------|----|--------|----------|
| 1 | 灵昭/灵鉴 | 灵瑾 | 发起安全审计 | dispatch-report |
| 2 | 灵瑾 | 大力/灵霄 | 审计出报告 | security-report（含漏洞列表）|
| 3 | 大力/灵霄 | 灵瑾 | 修复漏洞 | dev-report |
| 4 | 灵瑾 | 小七 | 复审确认 | security-report(conclusion=pass) |
| 5 | 小七 | (完成) | 验收 | approve-report |

---

## 链类型 I：子言直接派发链

```
子言 → 灵昭(方案) → 小七(调度) → ...
```

| 步骤 | from | to | action | 产出报告 |
|------|------|----|--------|----------|
| 1 | 子言 | 灵昭 | 提出需求 | (口头/面板消息) |
| 2 | 灵昭 | 小七 | 出方案+派发 | scheme-report + dispatch-report |
| 3+ | (后续走 A/B/C/D 链) | | | |

---

## 通用报告字段（所有链共用）

```json
{
  "template": "xxx-report",
  "conclusion": "pass",
  "from": "lingjian",
  "to": "lingyan",
  "cc": ["lingzhao", "xiaoqi", "lingxun"],
  "summary": "一句话摘要",
  "details": {},
  "chain_step": 4,
  "chain_total": 6
}
```

每个节点自动带 `chain_step` 和 `chain_total`，方便 Dashboard 渲染进度条。

---

## 链的存储

一条任务链存储在 `store/tasks/<task_id>.json`，结构：

```json
{
  "task_id": "msg-xxx",
  "initiator": "lingzhao",
  "chain_type": "A",
  "status": "running",
  "created_at": "...",
  "chain": [
    { "step": 1, "from": "lingzhao", "to": "xiaoqi", "action": "派发", "report": null, "status": "done", "started_at": "...", "completed_at": "..." },
    { "step": 2, "from": "xiaoqi", "to": "dali", "action": "调度开发", "report": {...}, "status": "done", ... },
    { "step": 3, "from": "dali", "to": "lingjian", "action": "开发", "report": {...}, "status": "running", ... }
  ]
}
```

**灵巡查询：** `chain[-1].to` = 当前该谁干活；`chain[-1].status` = running 但长时间没完成 → 催办。
