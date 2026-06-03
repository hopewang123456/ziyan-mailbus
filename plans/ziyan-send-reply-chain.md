# 子言发信回复链方案

## 目标
子言从面板发信给某个 agent 后，能收到对方的回复，并在面板里看到完整的对话链（已发→对方的回复）。

## 设计

### 后端改动（lib/api/handlers_inbox.py）

`handle_send_msg` 中，当 `from_ == 'ziyan'` 时，额外做两步：

1. **给自己（ziyan）的 inbox 存一条"已发送"记录**
   - 消息类型：`sent`
   - 内容：`[发给 {to}] {content}`
   - 字段额外加一个 `sent_to: <agent_name>`，`original_msg_id: <新生成的消息ID>`
   - 这样子言 inbox 里可以展示"我发了什么给谁"

2. **对目标 agent 的回复做关联**
   - 发送时把 `original_msg_id`（即发给目标 agent 的那条 msg_id）也记录到 ziyan 的已发送记录里
   - 当对方回复时，回复消息的 `original_msg_id` 会指向这个 id
   - API 层加一个新端点 `/api/ziyan-replies`，查询所有 agent 的 inbox 里 `original_msg_id` 指向子言发出的消息的回复

### 新增 API

**GET /api/ziyan-replies**
- 遍历所有 agent 的 inbox
- 收集所有 `type == 'reply'` 且 `original_msg_id` 存在于子言已发送消息列表中的
- 返回 `{ "<子言消息id>": [回复1, 回复2, ...] }`

### 前端改动（docs/index.html）

子言面板的 JS：

1. **发信弹窗发送后**，自动刷新面板（已有）
2. **已发送消息渲染**：从 `ziyan` inbox 中取出 `type == 'sent'` 的消息，展示为「已发送给 XX」
3. **调用 /api/ziyan-replies** 获取回复链
4. 每条已发送消息下方，如果有对方回复，展示回复内容

### 数据结构示例

```json
// ziyan inbox 中的已发送消息
{
  "id": "sent-20260603-xxxxx",
  "from": "ziyan",
  "to": "lingzhao",
  "type": "sent",
  "priority": "normal",
  "content": "能收到信吗？",
  "original_msg_id": "msg-20260603-xxxxx",
  "sent_to": "lingzhao",
  "status": "acknowledged",
  "created_at": "2026-06-03T14:26:51+0800"
}
```

```json
// 对方 inbox 中的回复消息（已有格式）
{
  "id": "reply-20260603-yyyyy",
  "from": "lingzhao",
  "type": "reply",
  "content": "收到了，内容...",
  "original_msg_id": "msg-20260603-xxxxx",
  "created_at": "2026-06-03T14:27:00+0800"
}
```

## 执行者
- 后端：灵霄 🔭
- 前端：小七 🦞（或者灵霄一起做了）
