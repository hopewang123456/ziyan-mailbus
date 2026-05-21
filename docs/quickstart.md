# ziyan-mailbus 快速开始

## 简介

ziyan-mailbus 是一个独立、解耦、轻量的**文件级消息总线系统**，专为多 Agent 团队设计。

核心能力：
- **文件即消息**：消息存 JSON 文件，零中间件依赖
- **双向确认**：CLI 推送 → Agent 即时回复 ack，不搞"推送即送达"的幻觉
- **优先级队列**：加急优先推送，普通排队，批量处理
- **故障隔离**：推送失败 3 次 → 写错误日志 → 监控 Agent 扫日志找修复方案
- **去中心化通信**：Agent 之间回信直接写目标 inbox，由总线递送

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
