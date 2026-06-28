# ziyan-mailbus 快速开始

## 简介

ziyan-mailbus 是一个独立、解耦、轻量的**文件级消息总线系统**，专为多 Agent 团队设计。

核心能力：
- **文件即消息**：消息存 JSON 文件，零中间件依赖
- **双向确认**：CLI 推送 → Agent 即时回复 ack，不搞"推送即送达"的幻觉
- **优先级队列**：加急优先推送，普通排队，批量处理
- **故障隔离**：推送失败 3 次 → 写错误日志 → 监控 Agent 扫日志找修复方案
- **去中心化通信**：Agent 之间回信直接写目标 inbox，由总线递送

## 团队规范

历史文件 [`STANDARD_PROCEDURE.md`](../STANDARD_PROCEDURE.md) 已弃用。现行边界见 [`docs/agent-layer-spec.md`](agent-layer-spec.md) 与 `mail/rules/common/`、`mail/skills/common/`。

## 安装

```bash
git clone https://github.com/hopewang123456/ziyan-mailbus.git
cd ziyan-mailbus
pip install -e .
```

## 快速开始

### 1. 初始化

```bash
# 创建数据目录和默认配置
mailbus init --data-dir /path/to/your/store
```

这会在 `/path/to/your/store` 下创建以下结构：
```
store/
├── config.json          # 总线配置
├── sent.json            # 发送记录
├── board.json           # 公告板
├── inbox/               # Agent 邮箱（agent-add 时创建）
├── queue/urgent/        # 加急队列
├── queue/normal/        # 普通队列
├── archive/             # 归档
└── errors/              # 错误日志
```

### 2. 注册 Agent

```bash
# 注册一个 Agent，CLI 是总线推送消息时的调用方式
mailbus agent-add agent-a --cli "your-cli --message" --role "你的角色"

# 不加 --cli 也可以（仅文件通信，无 CLI 推送）
mailbus agent-add agent-b --role "文件级通信"
```

注册后，Agent 的 inbox 中会自动写入一条系统消息，包含回复格式说明。

### 3. 启动总线

```bash
# 手动扫描一次
mailbus scan

# 或挂到 crontab，每分钟自动扫描
crontab -e
# 添加：
* * * * * cd /path/to/ziyan-mailbus && mailbus scan
```

### 4. 发送消息

```bash
# 发普通消息
mailbus send agent-a --msg "你好，请处理这个任务" --from lingzhao

# 发加急消息
mailbus send agent-a --msg "紧急！服务器挂了" --priority urgent --from lingzhao

# 发公告板（全员推送）
mailbus broadcast --msg "系统维护通知"
```

### 5. Agent 回复格式

Agent 收到推送后，需要即时回复总线以确认收到。

**确认收到（ack）：**

Agent 写文件到自己的 ack.json：
```json
{"action": "ack", "msg_id": "msg-20260521-001", "agent": "agent-a", "timestamp": "2026-05-21T12:00:05+0800"}
```

**标记已读（多条）：**
```json
{"action": "mark_read", "msg_ids": ["msg-1", "msg-2"], "agent": "agent-a", "timestamp": "2026-05-21T12:00:05+0800"}
```

**转发给其他 Agent：**
```json
{"action": "forward", "original_msg_id": "msg-1", "from": "agent-a", "to": "agent-b", "content": "请处理"}
```

详细格式见 [message-format.md](message-format.md)。

### 6. 查看状态

```bash
# 查看所有 Agent 的消息状态
mailbus status

# 查看指定 Agent
mailbus status --agent agent-a

# 查看失败消息
mailbus status --failed

# 查看错误日志
mailbus errors
```

### 7. 重试失败消息

```bash
# 重试所有失败消息（重置为 pending）
mailbus retry

# 重试单条
mailbus retry --msg-id msg-xxx

# 然后运行 scan 重新推送
mailbus scan
```

## CLI 命令总览

```bash
mailbus init              # 初始化目录结构
mailbus scan              # 扫描全员 inbox → 推送未读消息
mailbus send <agent>      # 手动发消息
mailbus broadcast         # 发公告板
mailbus ack               # Agent 确认收到
mailbus mark-read         # Agent 标记已读
mailbus status            # 查看消息状态
mailbus retry             # 重试失败消息
mailbus archive           # 手动触发归档
mailbus errors            # 查看错误日志
mailbus agent-add <name>  # 注册新 Agent
mailbus agent-remove      # 移除 Agent
```

## 配置参考

```json
{
  "project": "ziyan-mailbus",
  "version": "1.0.0",
  "data_dir": "/path/to/your/store",
  "ack_timeout": 30,
  "max_retries": 3,
  "archive_days": 7,
  "archive_max_messages": 300,
  "agents": {
    "agent-a": {
      "name": "agent-a",
      "role": "你的角色",
      "cli": "your-cli --message",
      "inbox": "/path/to/your/store/inbox/agent-a/inbox.json"
    }
  }
}
```

## 架构

详见 [ARCHITECTURE.md](ARCHITECTURE.md)。

---

## 通信规范

### 一、收到消息必须回信

所有 Agent 收到消息后必须完成以下回信流程：

1. **写 ack**：阅读消息内容后，在 `store/inbox/<你的名字>/ack.json` 中写入确认记录：
   ```json
   {"action": "ack", "msg_id": "消息ID", "agent": "你的名字", "timestamp": "ISO-8601时间戳"}
   ```
2. **回复（如需要）**：如果消息需要回复：
   - 常规消息 → 写入目标 Agent 的 inbox.json（messages 数组）
   - 任务消息（task/task_reply）→ 写入发送方的 inbox，`type` 设为 `task_reply`
3. **写回应到 board**：群组讨论在 `store/board.json` 中发帖

> ⚠️ 不写 ack = 系统认为你未收到，会持续催办

### 二、任务完成必须回信

接收任务消息后：
- 任务完成时，必须向 **任务发起方** 发送一条 `type: task_reply` 的回复消息
- 回复内容须包含完成状态（completed/failed/blocked）和必要的摘要
- 长期任务需阶段回报（进度更新也算回信）

### 三、超时自动催办

- 默认超时时间：**10 分钟**（可配置 `ack_timeout`）
- 超时流程：
  1. 消息 pending/pushed 超过 `timeout_minutes` 未 ack → 发催办给消息发送方
  2. 催办间隔：`timeout_minutes / 2`（默认5分钟）
  3. 超过 3 次仍无响应 → 标记为 failed
- 避免误判技巧：
  - 消息体可选设置 `timeout_minutes` 自定义超时（如长任务可设为 60）
  - 收到消息后先写 ack（我看到了），再处理（处理完回复）

### 四、离线处理

- 离线前写一条 `system:offline` 类型消息到自己的 inbox（系统读后暂停推送）
- 上线后第一条消息应包含 `system:online` 标记，系统恢复推送序列
- 离线期间的消息会在上线后一次性推送给 Agent

---

## 修订记录

| 日期 | 改动 | 作者 |
|------|------|------|
| 2026-06-01 | 增加通信规范（回信约束、超时催办、离线处理） | 小七 |
| 2026-05-21 | 初始版本 | 灵曦 |

