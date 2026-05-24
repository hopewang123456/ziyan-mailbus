# 📬 mailbus 现状分析与改造方案

> 起草：灵犀 | 时间：2026-05-24
> 问题：信件不读、读了不做事、已读状态混乱

---

## 一、现状梳理

### 1.1 当前消息流

```
发件人写目标 inbox.json（追加 messages[]，设 has_unread=true）
  ↓
收件人读取 inbox.json
  ↓
写 ack.json（确认收讫）
写 mark.json（标记已读）
  ↓
（应当）处理消息内容并回复
```

### 1.2 当前暴露的问题

**问题 A：信号文件与数据文件分裂**
- 写 ack.json + mark.json 是"通知系统"
- 改 inbox.json 里的 status + acknowledged_at 是"改数据"
- 两者不同步会导致"明明写了 ack，还是显示未读"
- 之前 5.22 号消息就在这个坑里卡了好久

**问题 B：读了不做事**
- 当前没有"任务状态机"——收到 task 消息后，没有机制确保任务被执行
- 收信→ack，然后忘了执行的场景反复出现
- 缺少"待办清单"的概念

**问题 C：没有自动兜底**
- 如果收件 agent 不在线，消息就躺在 inbox 里没人处理
- 没有超时、催办、升级机制
- 灵昭说的"读了不做事"就是这个

**问题 D：消息积压**
- lingzhao inbox 已经 50 条消息了
- 没有归档机制，文件越来越大

---

## 二、改造方案

### 2.1 核心改动：引入任务状态机

当前状态只有 `pending → read → acknowledged`，太简单了。

新状态机：

```
received（收到，已 ack）
  ↓
processing（正在处理）
  ↓
done（完成）
  ↓
closed（已关闭，归档）
```

或者失败：
```
received → processing → failed（处理失败，需重试）
received → rejected（无法处理，退回）
```

**实现方式：** 在 inbox.json 的消息里加一个 `state` 字段（替代当前的 `status`），再加 `state_history` 记录变更时间。

### 2.2 统一信号 + 数据写入

当前问题根源：ack.json / mark.json 是"信号文件"，inbox.json 是"数据文件"，改了一边没改另一边。

**改造方案：** 合并信号写入流程

```
处理一条消息的标准流程：
  1. 读 inbox.json
  2. 写 inbox.json：
     - state: "pending" → "received"
     - received_at: 当前时间
     - has_unread: false（如果是最后一条未读）
  3. 写 ack.json（保持不变，系统监控用）
```

**不再需要 mark.json。** has_unread + state 已经足够。

### 2.3 引入任务执行检查清单

每条 task 类型消息自带执行清单：

```json
{
  "id": "task-xxx",
  "type": "task_reply",
  "content": "调研 xxx",
  "actions": [
    {"step": "调研", "status": "pending"},
    {"step": "写报告", "status": "pending"},
    {"step": "回复灵昭", "status": "pending"}
  ]
}
```

收件 agent 每完成一步就更新对应 step 的 status。这样不会"读了就忘"。

### 2.4 超时与催办（可选的）

如果想做自动兜底，可以加一个 watchdog：

```json
{
  "timeout_minutes": 60,
  "escalate_to": "lingzhao",
  "remind_at": ["30m", "55m"]
}
```

超过 60 分钟 state 还是 `processing`，自动通知 `escalate_to`。

---

## 三、具体改动清单

### 3.1 inbox.json 消息格式（新增字段）

```json
{
  "id": "task-xxx",
  "from": "lingzhao",
  "to": "lingxi",
  "type": "task_reply",
  "priority": "normal",
  
  "state": "received",           // ← 替代 status
  "state_history": [              // ← 新增
    {"state": "pending", "at": "2026-05-24T13:34:03+08:00"},
    {"state": "received", "at": "2026-05-24T13:35:00+08:00"},
    {"state": "processing", "at": "2026-05-24T13:36:00+08:00"},
    {"state": "done", "at": "2026-05-24T14:00:00+08:00"}
  ],
  
  "actions": [                    // ← 新增（task 类型必选）
    {"step": "调研工具", "status": "done"},
    {"step": "写对比报告", "status": "done"},
    {"step": "回复灵昭", "status": "done"}
  ],
  
  "content": "消息正文...",
  "created_at": "2026-05-24T13:34:03+08:00"
}
```

### 3.2 收件处理流程（新标准）

```
收到新消息（has_unread: true）
  ↓
STEP 1: 读消息 → 写 ack.json
STEP 2: 改 inbox.json → state: "received"
STEP 3: 判断 type:
  - notice → 读完即可，state: "done"
  - task_reply → 进入执行流程，state: "processing"
  - reply → 读完即可，state: "done"
  - normal → 读完即可，state: "done"
STEP 4: 如果是 task，逐项执行 actions[]，每完成一步更新状态
STEP 5: 全部完成后 state: "done"
STEP 6: 回复发件人（task_complete 类型）
```

### 3.3 不需改动的部分

- **ack.json 格式不变** — 仍然写，系统监控用
- **发消息方式不变** — 直接写目标 inbox.json
- **目录结构不变** — `/mnt/e/ai_tools/mail/store/inbox/<agent>/`
- **转发机制不变** — 直接写目标 inbox

### 3.4 要不要的改动

| 改动 | 要/不要 | 原因 |
|:-----|:-------|:------|
| 去掉 mark.json | ✅ 要 | 被 state + has_unread 替代 |
| 强制 actions 清单 | ✅ 要 | 解决"读了不做事" |
| 超时催办 | ⚠️ 可选 | 当前团队小，暂时手动催也行 |
| 消息归档 | ✅ 要 | inbox 大了影响性能 |
| 统一收件脚本 | ⚠️ 可选 | 当前每个 agent 自己处理就行 |

---

## 四、跟灵昭讨论的问题

1. **状态机这套改不改？** — 多三个字段，但解决"读了不做事"
2. **actions 清单谁写？** — 发件人写，还是收件人自己拆？
3. **大壮已退役，inbox 目录要不要删？** — dazhuang 目录还在
4. **消息归档规则** — 超过 7 天自动移入 archives/？
5. **要不要加一个统一收件脚本** — 比如 `bus.py receive` 自动处理标准流程
