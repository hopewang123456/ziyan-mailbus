# ziyan-mailbus 消息格式文档

本文档定义了 ziyan-mailbus 的所有消息格式，供 Agent 开发者参考。

---

## 1. 消息状态流转

```
pending ──→ pushed ──→ acknowledged ──→ archived
               │
               ├→ failed（3次重试无 ack，需人工处理）
               │
               └→ resending（人工重推，附带断线说明）
```

| 状态 | 含义 |
|------|------|
| `pending` | 消息已写入 inbox，等待总线推送 |
| `pushed` | 总线已通过 CLI 推送给 Agent，等待 ack |
| `acknowledged` | Agent 已确认收到 |
| `failed` | 推送 3 次无 ack，进入错误日志 |
| `resending` | 人工重推中，附带断线前状态的说明 |
| `archived` | 已归档 |

---

## 2. 收件箱格式（inbox.json）

每个 Agent 在 `store/inbox/<agent_name>/inbox.json` 中维护自己的收件箱。

```json
{
  "agent": "lingxiao",
  "has_unread": true,
  "messages": [
    { /* Message 对象 */ },
    { /* Message 对象 */ }
  ],
  "since": "2026-05-21T12:00:00+0800"
}
```

| 字段 | 说明 |
|------|------|
| `agent` | Agent 名称 |
| `has_unread` | 是否有未读消息（总线据此判断是否推送） |
| `messages` | 消息列表 |
| `since` | 收件箱创建时间 |

---

## 3. 消息格式（inbox 中的 Message 对象）

```json
{
  "id": "msg-20260521-001",
  "from": "lingzhao",
  "to": "lingxiao",
  "priority": "normal",
  "type": "task",
  "content": "请检查 GitHub 仓库更新情况",
  "attachments": [],
  "reply_format": {
    "ack": {
      "file": "/mnt/e/ai_tools/mail/store/inbox/lingxiao/ack.json",
      "format": {
        "action": "ack",
        "msg_id": "msg-20260521-001",
        "agent": "lingxiao",
        "timestamp": "<ISO时间>"
      }
    },
    "mark_read": {
      "format": {
        "action": "mark_read",
        "msg_ids": ["msg-20260521-001"],
        "agent": "lingxiao",
        "timestamp": "<ISO时间>"
      }
    },
    "forward": {
      "description": "如需转发给其他 Agent，写文件到目标 inbox",
      "target_format": "/mnt/e/ai_tools/mail/store/inbox/<目标agent>/inbox.json",
      "format": {
        "action": "forward",
        "original_msg_id": "msg-20260521-001",
        "from": "lingxiao",
        "to": "<目标agent>",
        "type": "normal",
        "priority": "normal",
        "content": "...",
        "attachments": [],
        "timestamp": "<ISO时间>"
      }
    }
  },
  "status": "pending",
  "pushed_count": 0,
  "created_at": "2026-05-21T12:00:00+0800",
  "acknowledged_at": null
}
```

### 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | ✅ | 唯一消息 ID，格式 `msg-YYYYMMDD-XXXXX` |
| `from` | ✅ | 发件人 Agent 名称 |
| `to` | ✅ | 收件人 Agent 名称 |
| `priority` | ✅ | `normal`（普通）或 `urgent`（加急） |
| `type` | ✅ | `task` / `notice` / `question` / `system` |
| `content` | ✅ | 消息正文，纯文本，不宜过长 |
| `attachments` | ❌ | 附件路径列表（只传地址，不传文件本身） |
| `reply_format` | ✅ | Agent 回复总线时的格式说明 |
| `status` | ✅ | 当前状态 |
| `pushed_count` | ❌ | 已推送次数 |
| `created_at` | ❌ | 创建时间（ISO 8601） |
| `acknowledged_at` | ❌ | 确认时间 |

---

## 4. Agent 回复格式

Agent 收到推送后，需要即时回复总线。共有三种回复方式：

### 4.1 ack（确认收到）

**写入文件：** `store/inbox/<你的名字>/ack.json`

```json
{
  "action": "ack",
  "msg_id": "msg-20260521-001",
  "agent": "lingxiao",
  "timestamp": "2026-05-21T12:00:05+0800"
}
```

**说明：** 最常用的回复。Agent 收到消息后立即写这个文件，总线读到后把消息状态改为 `acknowledged`。

### 4.2 mark_read（标记已读，不回复）

**写入文件：** `store/inbox/<你的名字>/mark.json`

```json
{
  "action": "mark_read",
  "msg_ids": ["msg-20260521-001", "msg-20260521-002"],
  "agent": "lingxiao",
  "timestamp": "2026-05-21T12:00:05+0800"
}
```

**说明：** 适用于不回复也不转发的纯通知类消息。一次可以标记多条。

### 4.3 forward（转发给其他 Agent）

**写入文件：** 直接写目标 Agent 的 `inbox.json`

Agent 要把消息发给其他 Agent 时，**不调用总线 CLI**，而是直接写文件的 inbox：

```json
// 写入 /mnt/e/ai_tools/mail/store/inbox/xiaoqi/inbox.json
{
  "action": "forward",
  "original_msg_id": "msg-20260521-001",
  "from": "lingxiao",
  "to": "xiaoqi",
  "type": "task",
  "priority": "normal",
  "content": "灵昭让我检查仓库，需要你调度大力处理",
  "attachments": [],
  "timestamp": "2026-05-21T12:00:05+0800"
}
```

**重要：** Agent 之间转发消息是直接写目标 Agent 的 `inbox.json`，不是等总线推。总线在下一个 cron 周期会发现目标 inbox 有未读消息，然后推送给目标 Agent。

---

## 5. 公告板格式

```json
{
  "board": [
    {
      "id": "board-2026-05-21-1",
      "content": "系统维护通知：明天凌晨 2:00-4:00",
      "priority": "normal",
      "created_at": "2026-05-21T12:00:00+0800"
    }
  ],
  "created_at": "2026-05-21T12:00:00+0800"
}
```

公告板由 `bus.py broadcast` 写入，同时每条公告也会作为消息推送到每个 Agent 的 inbox。

---

## 6. 错误日志格式

```jsonl
{"ts": "2026-05-21T12:05:00+0800", "level": "ERROR", "msg_id": "msg-xxx", "to": "lingxiao", "error": "CLI 推送超时（3 次重试均无 ack）"}
{"ts": "2026-05-21T12:05:00+0800", "level": "WARN", "msg_id": "msg-yyy", "to": "dali", "error": "CLI 返回码非零"}
```

- 按周分文件：`store/errors/2026-W21.jsonl`
- 等级：`INFO` / `WARN` / `ERROR`
- 监控 Agent 应定期扫描此目录

---

## 7. 初始化系统消息

Agent 首次注册时，总线会在其 inbox 中写入一条系统消息：

```json
{
  "id": "sys-welcome-lingxiao",
  "from": "mailbus",
  "to": "lingxiao",
  "priority": "urgent",
  "type": "system",
  "content": "欢迎 lingxiao 加入 ziyan-mailbus 消息总线。",
  "reply_format": { /* 同上回复格式 */ },
  "system_info": {
    "inbox_location": "/mnt/e/ai_tools/mail/store/inbox/lingxiao/inbox.json",
    "inbox_format": "/mnt/e/ai_tools/mail/store/inbox/<目标agent>/inbox.json",
    "registered_agents": ["lingzhao", "lingxi", "xiaoqi", "yige", "lingxiao", "dali", "dazhuang"],
    "bus_cli_location": "/mnt/e/ai_tools/mail/bus.py",
    "bus_cron_interval": "每分钟扫描一次",
    "ack_timeout": "30秒"
  },
  "status": "pending",
  "created_at": "2026-05-21T12:00:00+0800"
}
```

---

## 8. 安全边界

| 规则 | 说明 |
|------|------|
| Agent 仅能写自己的目录 | ack.json / mark.json 只能写自己的 inbox 目录 |
| Agent 可以读其他 Agent 的 inbox | 以便转发消息 |
| Agent 不能调总线 CLI | CLI（scan / send / broadcast）由运维人员使用 |
| 总线系统文件只读 | config.json / sent.json / errors 只有总线自己写 |
