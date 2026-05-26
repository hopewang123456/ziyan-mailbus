# ziyan-mailbus 架构文档

> 多 Agent 消息总线系统 — 独立、解耦、轻量的文件级消息中间件
> 版本: v2.0.0
> 协议: MIT

---

## 1. 核心理念

**消息总线是一个独立的文件级消息中间件，不依赖任何 Agent 框架（Hermes / OpenClaw / Cline 等）**

- 消息存 JSON 文件，零中间件依赖（不需要 Redis / RabbitMQ / DB）
- 发送方写 inbox JSON → 总线 cron 扫描 → CLI 推送 → Agent 即时回复 ack → 总线更新状态
- Agent 之间互相回信也走文件（写目标 inbox），由总线下一次 cron 递送
- 即使所有 Agent 都没启动，总线也能接收消息、排队、记录推送失败状态

---

## 2. 数据流

```
                      ┌─────────────────────────────────────┐
                      │      ziyan-mailbus（总线）            │
                      │                                     │
                      │  cron 每分钟: scan                    │
                      │    1. 扫所有 inbox → has_unread       │
                      │    2. 按 加急队列 > 普通队列 推送       │
                      │    3. 批量推送（同 agent 所有未读一起）  │
                      │    4. 等 agent 回复 ack                │
                      │    5. 无 ack → 重试 ×3 → 写 error log │
                      └───────┬──────────────────────┬───────┘
                              │ CLI 推送              │ agent 回复
                              ▼                      ▲
                    ┌──────────────────┐    ┌──────────────────┐
                    │    Agent A       │    │    Agent B       │
                    │  (Hermes/CLI/…)  │    │  (OpenClaw/…)    │
                    └──────────────────┘    └──────────────────┘
                              │                      │
                              └────── 文件 ──────────┘
                            Agent 间回信直接写目标 inbox
```

---

## 3. 目录结构

```
/mnt/e/ai_tools/mail/
│
├── bus.py                    # 入口脚本（CLI 命令入口）
│
├── lib/                      # 核心模块
│   ├── __init__.py
│   ├── models.py             # 数据模型定义（消息/队列/状态常量）
│   ├── scanner.py            # 扫描 inbox → 构建推送队列
│   ├── pusher.py             # CLI 推送 + ack 等待 + 重试
│   ├── ack_handler.py        # 处理 agent 回复（ack / forward / mark_read）
│   ├── archiver.py           # 已读消息归档
│   └── utils.py              # 文件锁、日志、ID 生成等通用工具
│
├── store/                    # 数据目录（运行时生成）
│   ├── config.json           # 总线配置（各 agent 注册信息）
│   ├── sent.json             # 发送记录（消息 ID → 状态）
│   ├── board.json            # 公告板
│   │
│   ├── inbox/                # 各 agent 邮箱
│   │   ├── lingzhao/
│   │   │   └── inbox.json    # {has_unread, messages: [...]}
│   │   ├── lingxi/
│   │   │   └── inbox.json
│   │   ├── xiaoqi/
│   │   │   └── inbox.json
│   │   ├── yige/
│   │   │   └── inbox.json
│   │   ├── lingxiao/
│   │   │   └── inbox.json
│   │   ├── dali/
│   │   │   └── inbox.json
│   │   └── dazhuang/
│   │       └── inbox.json
│   │
│   ├── queue/                # 推送队列（总线内部使用）
│   │   ├── urgent/           # 加急队列（.json 文件逐个排队）
│   │   └── normal/           # 普通队列
│   │
│   ├── archive/              # 已读消息归档
│   │   ├── lingzhao/         # 每人独立归档目录
│   │   ├── lingxi/
│   │   ├── xiaoqi/
│   │   ├── yige/
│   │   ├── lingxiao/
│   │   ├── dali/
│   │   └── dazhuang/
│   │
│   └── errors/               # 推送失败日志（小七定时扫这个目录）
│       └── 2026-W21.jsonl    # 按周分文件
│
├── examples/
│   └── config.example.json   # 示例配置（开源使用）
│
├── tests/
│   ├── test_scanner.py
│   ├── test_pusher.py
│   ├── test_ack_handler.py
│   └── test_archiver.py
│
├── docs/
│   ├── quickstart.md
│   ├── message-format.md     # 消息格式 + 回复格式文档（对 agent 开发者的接口文档）
│   └── architecture.md       # 本文件
│
├── README.md
├── LICENSE                   # MIT
├── pyproject.toml
└── CHANGELOG.md
```

---

## 4. 消息模型

### 4.1 消息状态

```
pending ──→ pushed ──→ acknowledged ──→ archived
               │                            ↑
               ├→ failed（3次重试失败）       │
               │    └→ 写 errors/          7天 / 300条
               └→ resending（重新发送）
```

| 状态 | 含义 |
|------|------|
| `pending` | 消息已写入 inbox，等待总线推送 |
| `pushed` | 总线已通过 CLI 推送给 agent，等待 ack |
| `acknowledged` | agent 即时回复了"收到" |
| `failed` | 推送 3 次无 ack，进入错误日志 |
| `resending` | 人工/自动重新推送（附带断线前状态的说明） |
| `archived` | 已归档 |

### 4.2 消息格式（inbox.json 中的消息条目）

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
    "forward": {
      "description": "如需转发给其他 agent，直接写文件到目标 inbox",
      "target_format": "/mnt/e/ai_tools/mail/store/inbox/<agent_name>/inbox.json",
      "format": {
        "action": "forward",
        "original_msg_id": "msg-20260521-001",
        "from": "lingxiao",
        "to": "<目标agent>",
        "type": "normal",
        "priority": "normal",
        "content": "...",
        "attachments": []
      }
    },
    "mark_read": {
      "description": "仅标记已读，不回复也不转发",
      "format": {
        "action": "mark_read",
        "msg_ids": ["msg-20260521-001"],
        "agent": "lingxiao"
      }
    }
  },
  "status": "pending",
  "pushed_count": 0,
  "created_at": "2026-05-21T12:00:00",
  "acknowledged_at": null
}
```

### 4.3 inbox.json 整体结构

```json
{
  "agent": "lingxiao",
  "has_unread": true,
  "messages": [
    { /* 消息 1 */ },
    { /* 消息 2 */ }
  ],
  "since": "2026-05-21T12:00:00"
}
```

---

## 5. 回复格式（agent 回复总线用）

### 5.1 ack（确认收到）

```json
{
  "action": "ack",
  "msg_id": "msg-20260521-001",
  "agent": "lingxiao",
  "timestamp": "2026-05-21T12:00:05"
}
```

写入: `/mnt/e/ai_tools/mail/store/inbox/<agent>/ack.json`

### 5.2 mark_read（仅标记已读）

```json
{
  "action": "mark_read",
  "msg_ids": ["msg-20260521-001", "msg-20260521-002"],
  "agent": "lingxiao",
  "timestamp": "2026-05-21T12:00:05"
}
```

写入: `/mnt/e/ai_tools/mail/store/inbox/<agent>/mark.json`

### 5.3 forward（转发给其他 agent）

```json
{
  "action": "forward",
  "original_msg_id": "msg-20260521-001",
  "from": "lingxiao",
  "to": "xiaoqi",
  "type": "task",
  "priority": "normal",
  "content": "灵昭让我检查仓库，发现有两个仓库需要更新，请调度大力处理",
  "attachments": [],
  "timestamp": "2026-05-21T12:00:05"
}
```

写入: `/mnt/e/ai_tools/mail/store/inbox/<目标agent>/inbox.json`
（注意：要更新目标 inbox 的 `messages` 数组 + 设 `has_unread: true`）

---

## 6. CLI 命令

```bash
## 总线主命令
bus.py scan                          # 扫描全员 inbox → 推送未读消息
bus.py send <agent> --from <sender>  # 手动发消息给指定 agent
              --msg <content>
              [--priority urgent]
              [--type task|notice|question]
              [--attachment <path>]

bus.py broadcast --msg <content>     # 发公告板（推送给所有 agent）
                 [--priority urgent]

bus.py ack --msg-id <id>             # agent 确认收到（agent 调用）
bus.py mark-read --msg-ids <id,...>  # agent 标记已读（agent 调用）

bus.py status                        # 查看所有消息状态
bus.py status --agent <name>         # 查看指定 agent 的消息
bus.py status --failed               # 查看所有失败消息

bus.py retry                         # 重试所有 failed 消息
bus.py retry --msg-id <id>           # 重试单条消息

bus.py archive                       # 手动触发归档
bus.py errors                        # 查看错误日志

## 管理命令
bus.py agent-add <name>              # 注册新 agent
bus.py agent-remove <name>           # 移除 agent
bus.py init                          # 初始化目录结构 + 写入系统通知
```

---

## 7. 推送策略

### 7.1 批量推送

- 每次 scan 扫描到某个 agent 有 N 条未读消息
- **一次把所有未读消息推过去**（不一条条等）
- 每条消息附带独立的 reply_format，agent 可以逐条回复

### 7.2 队列优先级

```
加急队列（urgent）         普通队列（normal）
    │                           │
    └───────── 先推 ────────────┘
               │
               ▼
           CLI 推送
```

- 加急队列的 agent 优先推送
- 同队列内按消息时间排序，先进先推
- 同发件人的消息不串行等待（不阻塞其他发件人的消息）

### 7.3 加急判断

- **发信人标记**：消息的 `priority` 字段为 `urgent`
- **总线自动识别**：content 中包含明确的"紧急"字样时自动升为加急
- **不做自作主张**：没有明显紧急字样的不让改

### 7.4 推送超时与重试

```
推送 agent → 等待 ack（默认 30 秒超时）
  ↓
有 ack → 状态改为 acknowledged
无 ack → 再次推送（重试 1）
  ↓
有 ack → acknowledged
无 ack → 再次推送（重试 2）
  ↓
有 ack → acknowledged
无 ack → 状态改为 failed → 写 errors 日志
  ↓
小七定时任务扫 errors 目录
→ 发现失败记录 → 找修复方案
→ 人工决定重新推送时附带说明：
  "这是之前推送未成功的消息，请确认是否已完成或是否需要继续执行"
```

---

## 8. 归档策略

### 8.1 触发条件

消息状态变为 `acknowledged` 后，满足以下任一条件即触发归档：

- **时间条件**：距今超过 7 天
- **数量条件**：inbox 中消息数量超过 300 条

### 8.2 归档过程

```
inbox.json 中的 acknowledged 消息
  ↓ 检查条件
满足条件 → 从 inbox.messages 中移除 → 写入 archive/<agent>/<周>.jsonl
不满足 → 留在 inbox 中
```

### 8.3 归档文件格式

JSON Lines（`.jsonl`），每行一条完整消息 JSON，按周分文件：

```
/mnt/e/ai_tools/mail/store/archive/lingxiao/2026-W21.jsonl
/mnt/e/ai_tools/mail/store/archive/lingxiao/2026-W22.jsonl
```

---

## 9. 错误处理与告警

### 9.1 错误日志格式

```jsonl
{"ts": "2026-05-21T12:05:00", "level": "ERROR", "msg_id": "msg-20260521-001", "to": "lingxiao", "error": "CLI 推送超时（3 次重试均无 ack）", "action": "需人工处理"}
{"ts": "2026-05-21T12:05:00", "level": "WARN", "msg_id": "msg-20260521-002", "to": "dali", "error": "CLI 返回码非零，agent 可能未启动", "action": "检查 agent 是否在线"}
```

- 等级：`INFO` / `WARN` / `ERROR`
- 写入: `/mnt/e/ai_tools/mail/store/errors/2026-W21.jsonl`（按周分文件）
- 每天第一次写入时自动清理 30 天前的错误日志

### 9.2 小七监控

- 小七的 cron 定时任务每分钟扫描 errors 目录
- 发现新的 ERROR 级别记录 → 分析错误 → 找修复方案
- 修复完成后人工触发 `bus.py retry --msg-id <id>`

---

## 10. 初始化流程（新 Agent 上线）

1. **总线注册**：`bus.py agent-add <name>`
2. 总线创建 `store/inbox/<name>/` 目录 + `inbox.json`（`has_unread: false`, `messages: []`）
3. 总线在 inbox 中写入第一条系统消息，包含：
   - 本总线简介
   - 自己 inbox 路径
   - 其他 agent inbox 路径格式
   - ack / forward / mark_read 的回复格式
4. Agent 启动后，读到这条系统消息 → 知道怎么回复总线

### 初始化系统消息示例

```json
{
  "id": "sys-welcome-001",
  "from": "mailbus",
  "to": "<agent_name>",
  "priority": "urgent",
  "type": "system",
  "content": "欢迎加入 ziyan-mailbus 消息总线。以下是你的通信配置：",
  "reply_format": {
    "ack": { "file": "/mnt/e/ai_tools/mail/store/inbox/<agent_name>/ack.json", "format": {"action": "ack", "msg_id": "<id>", "agent": "<agent_name>", "timestamp": "<ISO时间>"} },
    "forward": { "target_format": "/mnt/e/ai_tools/mail/store/inbox/<目标agent>/inbox.json", "format": {"action": "forward", "original_msg_id": "<id>", "from": "<agent_name>", "to": "<目标>", "type": "normal", "content": "..."} },
    "mark_read": { "format": {"action": "mark_read", "msg_ids": ["<id>"], "agent": "<agent_name>"} }
  },
  "system_info": {
    "inbox_location": "/mnt/e/ai_tools/mail/store/inbox/<agent_name>/inbox.json",
    "inbox_format": "/mnt/e/ai_tools/mail/store/inbox/<目标agent>/inbox.json",
    "registered_agents": ["lingzhao", "lingxi", "xiaoqi", "yige", "lingxiao", "dali", "dazhuang"],
    "bus_cli_location": "/mnt/e/ai_tools/mail/bus.py",
    "bus_cron_interval": "每分钟扫描一次",
    "ack_timeout": "30秒"
  }
}
```

---

## 11. config.json 结构

```json
{
  "project": "ziyan-mailbus",
  "version": "1.0.0",
  "data_dir": "/mnt/e/ai_tools/mail/store",
  "ack_timeout": 30,
  "max_retries": 3,
  "archive_days": 7,
  "archive_max_messages": 300,
  "agents": {
    "lingzhao": {
      "name": "灵昭",
      "role": "方案设计",
      "cli": "hermes run --profile lingzhao --message",
      "inbox": "/mnt/e/ai_tools/mail/store/inbox/lingzhao/inbox.json"
    },
    "lingjin": {\n      "name": "灵瑾",\n      "role": "网络安全",\n      "cli": "hermes run --profile lingjin --message",\n      "inbox": "/mnt/e/ai_tools/mail/store/inbox/lingjin/inbox.json"\n    },\n    "lingxi": {\n      "name": "灵犀",\n      "role": "技术雷达",\n      "cli": "hermes run --profile lingxi --message",\n      "inbox": "/mnt/e/ai_tools/mail/store/inbox/lingxi/inbox.json"\n    },
    "xiaoqi": {
      "name": "小七",
      "role": "调度",
      "cli": "openclaw --run-task --message",
      "inbox": "/mnt/e/ai_tools/mail/store/inbox/xiaoqi/inbox.json"
    },
    "yige": {
      "name": "一哥",
      "role": "运营",
      "cli": "openclaw --run-task --message",
      "inbox": "/mnt/e/ai_tools/mail/store/inbox/yige/inbox.json"
    },
    "lingxiao": {
      "name": "灵霄",
      "role": "技术负责人",
      "cli": "cline --provider openai-compatible -s \"...\" --message",
      "inbox": "/mnt/e/ai_tools/mail/store/inbox/lingxiao/inbox.json"
    },
    "dali": {
      "name": "大力",
      "role": "编码",
      "cli": "opencode --message",
      "inbox": "/mnt/e/ai_tools/mail/store/inbox/dali/inbox.json"
    },
    "dazhuang": {
      "name": "大壮",
      "role": "编码/审查",
      "cli": "aider --message",
      "inbox": "/mnt/e/ai_tools/mail/store/inbox/dazhuang/inbox.json"
    }
  }
}
```

（开源版本的 config.example.json 会将路径和 agent 列表清空，让用户自己填）

---

## 12. 安全边界

| 规则 | 说明 |
|------|------|
| 各 agent 仅能写自己的 inbox 目录 | ack / mark_read 只能写自己的目录 |
| 各 agent 可以读其他 agent 的 inbox | 这样才能转发消息给其他 agent |
| 各 agent 不能调 CLI | CLI（bus.py scan / send / broadcast / retry）只有总线 cron 和运维人员使用 |
| 总线系统文件不可被 agent 写入 | config.json / sent.json / errors 只有总线自己写 |

---

## 13. 开源注意事项

- 目录路径（`/mnt/e/ai_tools/`）和 agent 配置是**部署实例私有数据**
- `store/` 目录不提交 git（`.gitignore` 中忽略）
- `config.json` 不提交，提交 `examples/config.example.json`
- 所有路径在示例配置和文档中写相对路径或 `$DATA_DIR` 占位符
- agent 的 CLI 调用方式（Hermes/OpenClaw/Cline/OpenCode/Aider）作为示例，用户按需替换

---

## 14. 开发计划

### Phase 1：核心功能
- [ ] 目录结构初始化 + bus.py init
- [ ] 消息模型 + config.json
- [ ] scanner：扫描 inbox → 构建队列
- [ ] pusher：CLI 推送 + ack 等待 + 3次重试
- [ ] ack_handler：处理 agent 回复
- [ ] scan 命令（集成 scanner + pusher + ack_handler 的完整流程）

### Phase 2：周边功能
- [ ] send / broadcast 命令
- [ ] status / retry / errors 命令
- [ ] 归档逻辑
- [ ] agent-add / agent-remove

### Phase 3：测试与文档
- [ ] 单元测试
- [ ] 集成测试（Mock CLI 模拟 agent 回复）
- [ ] 中文文档（message-format.md / quickstart.md）
- [ ] 示例配置

### Phase 4：开源准备
- [ ] 隐私数据剥离审查
- [ ] README 完善
- [ ] LICENSE（MIT）
- [ ] pyproject.toml
- [ ] GitHub 仓库创建（private → stable → public）

---

> **本文件是设计阶段的架构文档，实现时可能根据实际遇到的边界情况进行调整。**
