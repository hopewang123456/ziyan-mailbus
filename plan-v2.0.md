# ziyan-mailbus v2.0 执行计划

## P0.1 — 消息协议标准化

### 目标
将消息从"自然语言驱动"改为"结构化字段驱动"，Agent 不再需要从文本中猜要做什么。

### 改动点

#### 1.1 扩展 Message 模型（lib/models.py）
- 新增 `action` 字段：dict，包含 ack/reply_to/execute/forward_to/store_memory
- 新增 `task` 字段：dict，包含 summary/assignee/status/deadline/deliverable
- 标准化 `type` 枚举：notice / task / task_reply / question / forward / forward_reply / broadcast / system / error_report
- `action` 的默认值根据 type 自动推断（不用每条消息都写全）

#### 1.2 修改推送文本生成（lib/pusher.py）
- 去掉自然语言解析转发的正则匹配
- 改为直接读消息的 `action` 字段：
  - `action.forward_to` → 生成转发指令+格式
  - `action.reply_to` → 生成回复指令+格式
  - `action.execute` → 生成执行指令
  - `action.store_memory` → 生成存记忆指令
- ack 指令永远保留

#### 1.3 占位符系统升级（lib/pusher.py resolve_cli）
- 新增 `ACTION` 占位符：可在 agent_types 模板中用
- Agent 类型模板可以微调各框架对 action 的处理方式

### 验证
- 所有现有测试通过
- 发送一条 `type=forward_reply` + `action.forward_to=["一哥"]` 的消息，Agent 能正确转发+回复

---

## P0.2 — 任务追踪 + 催办 + 错误回执

### 目标
每条消息从发起到完成的完整状态追踪，超时自动催办，执行失败有标准回执。

### 改动点

#### 2.1 新增 lib/tracker.py
- `TaskTracker` 类，管理 `store/tasks/` 目录
- 方法：`create_task`, `update_status`, `add_hop`, `get_chain`
- 数据格式：task_id + status(enum) + chain[hops] + error + reminded_count

#### 2.2 新增催办逻辑（lib/pusher.py 或 lib/reminder.py）
- scan 时检查：pushed 超过可配时间（默认 5 分钟）没 ack 的消息
- 自动重推 + `reminded_count++`
- 重推 3 次无 ack → 状态变 timeout → 写 error → 升级通知给发件人

#### 2.3 错误回执处理（lib/ack_handler.py）
- 识别 `type=error_report` 的消息
- 解析 `error.code / reason / trace` 写入 task tracker
- 更新 task 状态为 failed

#### 2.4 追踪链更新（lib/scanner.py）
- scan 时检测消息是否有 `forward_chain`
- 检查当前 Agent 是否完成了自己的 hop
- 更新 chain 状态

### 验证
- 发送一个需要多跳的任务，检查 `store/tasks/` 生成完整追踪链
- 模拟 Agent 不 ack，验证催办触发
- 模拟 Agent 发错误回执，验证 task 状态变 failed
