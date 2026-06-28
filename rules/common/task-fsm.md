# Task / Step 状态机

SoT 实现：`mail/lib/task_fsm.py`。

- done 仅认 `store/msg-results/{msg_id}.json`
- 禁止 phantom 回执（只写 replies 不算完成）
- Work Order：`store/work-orders/{task_id}/step-{step_id}.md`
