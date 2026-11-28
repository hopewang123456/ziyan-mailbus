# task-fsm

任务状态机（默认规则示例）。

## 状态
- `created`：任务已创建，尚未分派。
- `assigned`：已分派给执行者。
- `running`：执行中。
- `needs_info`：缺少信息，等待补充。
- `needs_human`：需要人工决策或介入。
- `completed`：成功完成（终态）。
- `failed`：执行失败（终态）。
- `cancelled`：已取消（终态）。

## 允许的主要迁移
- `created -> assigned -> running`
- `running -> completed | failed | needs_info | needs_human`
- `needs_info -> running | cancelled`
- `needs_human -> running | cancelled`
- `assigned -> cancelled`

## 约束
- 终态任务不得再回到执行中；确需重做应创建新任务或新尝试。
- 每次状态变更应带时间戳与操作者；失败必须带原因。
- 重复回调不得改变终态结果。
