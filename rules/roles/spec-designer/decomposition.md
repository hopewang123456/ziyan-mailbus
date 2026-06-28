# 方案设计 — 任务分解纪律（Phase 6 · P6-D01–D03）

> 适用工种：spec-designer（灵昭 · role_type=1）  
> 工单模板：`mail/rules/common/work-order-template.md`  
> msg-results schema：`mail/rules/schemas/decomposition-result.schema.json`

## 1. 模糊任务 → 停设计步，回子言

当 **Intent / Scope / Acceptance** 任一缺失、矛盾、或依赖未确认的外部决策时：

1. **不得** push 开发（coding-executor / developer · role_type=8）
2. msg-results 设 `conclusion: clarifications_needed` 或 `return_to_owner`
3. 在 `decomposition.clarifications_needed[]` 列出待确认问题（每条含 `question`、`context`、`blocking: true`）
4. FSM 阻塞并写入 human_queue（type=`owner_confirmation`），Dashboard 展示「待主人确认」

对齐后由子言 resolve human_queue → 设计步重开或更新 Intent 后再拆单。

## 2. 复杂任务 → subtasks[] DAG

满足任一条件视为**复杂**，必须产出有序子任务列表：

- `constraints.require_decomposition: true`
- tier 为 `L` / `S`
- 计划链含 **>1** 个开发步或 **≥3** 个后续 role_type
- 跨模块 / 多工种 / 多个可独立验收增量

产出要求：

- `decomposition.status: ready`（或 `simple` 若明确可一跳开发）
- `decomposition.subtasks[]`：每项含 `id`、`title`、`role_type`、`assignee_hint`（可选）、`acceptance`、`depends_on[]`
- 子任务按拓扑序写入 `chain[0].planned_role_types`，FSM **逐步** push，禁止 mega 工单

## 3. 简单明确任务

- 可设 `decomposition.status: simple` 并省略 `subtasks`
- 允许设计步完成后直接进入下一 planned role_type

## 4. 禁止

- 模糊需求直推大力/灵云猜实现
- 单条工单塞满全 pipeline（「一股脑」coding）
- 无 msg-results / 无 decomposition 字段即标 done 并推开发

## 5. 验收（设计步 msg-results 示例）

```json
{
  "task_id": "example-task",
  "step_id": "s1",
  "agent": "lingzhao",
  "role_type": 1,
  "conclusion": "done",
  "summary": "方案已拆为 3 个可独立验收增量",
  "decomposition": {
    "status": "ready",
    "subtasks": [
      {
        "id": "st-api",
        "title": "实现 REST API 层",
        "role_type": 8,
        "assignee_hint": "dali",
        "acceptance": "pytest tests/test_api.py 全绿",
        "depends_on": []
      },
      {
        "id": "st-ui",
        "title": "Dashboard 联调",
        "role_type": 8,
        "assignee_hint": "lingxiao",
        "acceptance": "test_phase4_dashboard 相关用例通过",
        "depends_on": ["st-api"]
      }
    ]
  }
}
```

模糊示例：

```json
{
  "conclusion": "clarifications_needed",
  "decomposition": {
    "status": "clarifications_needed",
    "clarifications_needed": [
      {
        "question": "支付走微信还是支付宝？",
        "context": "Scope 中 payment 未指定渠道",
        "blocking": true
      }
    ]
  }
}
```
