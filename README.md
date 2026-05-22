# ziyan-mailbus

多 Agent 消息总线系统 — 独立、解耦、轻量的**文件级消息中间件**，专为多 Agent 团队设计。

> 不需要 Redis / RabbitMQ / 数据库。消息存 JSON 文件，CLI 推送，Agent 即时回复 ack。

## 设计哲学

- **文件即通信**：消息存 JSON 文件，零中间件依赖。备份=cp，迁移=scp
- **双向确认**：CLI 推送 + Agent 主动 ack，不搞"推送即送达"的幻觉
- **先队列再推送**：加急排队优先，普通排队顺序，同 Agent 批量推送
- **故障隔离**：推送失败 3 次 → 写错误日志 → 监控 Agent 扫日志找修复方案
- **Agent 类型抽象**：统一 `agent_types` 配置，支持 Hermes / OpenClaw / Cline / OpenCode 等框架

## 快速开始

```bash
# 1. 安装
git clone https://github.com/hopewang123456/ziyan-mailbus.git
cd ziyan-mailbus
pip install -e .

# 2. 初始化
mailbus init --data-dir /path/to/your/store

# 3. 注册 Agent
mailbus agent-add agent-a --cli "your-cli --message" --role "你的角色"

# 4. 启动总线（cron，每分钟扫描）
crontab -e
# 添加：* * * * * cd /path/to/ziyan-mailbus && mailbus scan

# 5. 发消息
mailbus send agent-a --msg "你好，请处理这个任务" --from lingzhao
mailbus broadcast --msg "系统维护通知"

# 6. 查看状态
mailbus status
mailbus status --failed
```

## 核心特性

| 特性 | 说明 |
|------|------|
| **零依赖** | 纯 Python + 文件系统，不需要 Redis / MQ / DB |
| **双向确认** | 推送 → Agent 写 ack → 总线更新状态，不丢消息 |
| **优先级队列** | 加急消息优先推送，普通消息排队 |
| **Agent 类型抽象** | 统一配置模板，支持 6 种 Agent 框架（见下方） |
| **公告板** | `broadcast` 一键全员推送 |
| **错误日志** | 推送失败写 JSONL 日志，按周分文件 |
| **记忆同步** | 可选桥接 AgentMemory，消息自动持久化（见下方） |
| **归档策略** | 已 ack 超 7 天 / 超 300 条自动归档 |

### 支持的 Agent 框架

| 类型 | CLI 模板 | 框架 |
|------|----------|------|
| `hermes` | `hermes chat -q 'MSG' -Q` | Hermes Agent |
| `hermes_profile` | `hermes chat -q 'MSG' -Q --profile PROFILE` | Hermes 多 Profile |
| `openclaw` | `openclaw agent --local --agent AGENT --message 'MSG'` | OpenClaw Gateway |
| `cline` | `cline 'MSG' --provider openai-compatible` | Cline CLI |
| `opencode` | `opencode run 'MSG' --dangerously-skip-permissions MODEL` | OpenCode |
| `none` | 纯文件通信，无 CLI 推送 | 手动调度 |

## CLI 命令总览

```bash
mailbus init                        # 初始化目录结构
mailbus scan                        # 扫描全员 inbox → 推送未读消息
mailbus send <agent>                # 手动发消息（--priority urgent --from 发件人）
mailbus broadcast                   # 发公告板（全员推送）
mailbus ack --msg-id <ID>           # Agent 确认收到
mailbus mark-read --msg-ids <ID>    # Agent 标记已读
mailbus status [--agent <名>]       # 查看消息状态
mailbus status --failed             # 查看失败消息
mailbus retry [--msg-id <ID>]       # 重试失败消息
mailbus archive                     # 手动触发归档
mailbus errors                      # 查看错误日志
mailbus agent-add <名>              # 注册新 Agent
mailbus agent-remove <名>           # 移除 Agent
```

## Agent 回复格式

Agent 收到推送后，写文件回复总线（不调 CLI）：

**确认收到（ack.json）：**
```json
{"action":"ack","msg_id":"msg-xxx","agent":"agent-a","timestamp":"2026-05-21T12:00:05+0800"}
```

**标记已读（mark.json）：**
```json
{"action":"mark_read","msg_ids":["msg-xxx","msg-yyy"],"agent":"agent-a","timestamp":"2026-05-21T12:00:05+0800"}
```

**转发给其他 Agent：**
直接写目标 Agent 的 `inbox.json`（追加到 `messages` 数组 + 设 `has_unread: true`）

## AgentMemory 记忆同步（可选）

mailbus 可以自动将已 ack 的消息同步到 [AgentMemory](https://github.com/AgentMemory/AgentMemory)，保证 Agent 重启后能检索到历史消息。

```bash
# 先确保 AgentMemory 在 http://localhost:3111 运行
# 然后在 cron 中 chain 调用：
* * * * * cd /path/to/ziyan-mailbus && mailbus scan && python3 mailbus-memory-bridge.py --data-dir /path/to/store
```

消息以标签格式存入记忆：`[agent:xxx] [from:yyy] [msg_id:zzz] <消息内容>`

## 多模型 Fallback

每个 agent 可以配置多个 LLM 模型别名，总线按顺序试，通了一个就停：

```json
{
  "agents": {
    "dali": {
      "type": "opencode",
      "models": ["deepseek-chat", "qwen-max", "zhipu-4"]
    }
  },
  "agent_types": {
    "models": {
      "deepseek-chat": {
        "opencode": "--model deepseek/deepseek-chat",
        "cline": "--provider openai-compatible"
      },
      "qwen-max": {
        "opencode": "--model qwen/qwen-max",
        "cline": "--provider openai-compatible"
      },
      "zhipu-4": {
        "opencode": "--model zhipu/glm-4",
        "cline": "--provider openai-compatible"
      }
    }
  }
}
```

CLI 模板中用 `MODEL` 占位符，总线自动根据 agent 的 `models` 列表和类型解析出对应的参数。

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
      "name": "Agent A",
      "role": "描述",
      "type": "hermes",
      "inbox": "/path/to/your/store/inbox/agent-a/inbox.json"
    }
  },
  "agent_types": {
    "hermes": {
      "push": "hermes chat -q 'MSG' -Q",
      "description": "Hermes Agent 实例"
    }
  }
}
```

## 项目结构

```
ziyan-mailbus/
├── bus.py                        # 入口脚本（CLI 命令入口）
├── lib/
│   ├── __init__.py
│   ├── models.py                 # 数据模型
│   ├── scanner.py                # 扫描 inbox → 构建推送队列
│   ├── pusher.py                 # CLI 推送 + ack 等待 + 重试
│   ├── ack_handler.py            # 处理 Agent 回复
│   ├── archiver.py               # 已读消息归档
│   └── utils.py                  # 文件锁、日志、ID 生成
├── mailbus-memory-bridge.py      # AgentMemory 桥接（可选）
├── store/                        # 数据目录（运行时生成）
├── tests/                        # 测试套件
├── docs/                         # 文档
├── README.md
├── CHANGELOG.md
├── LICENSE
└── pyproject.toml
```

## 架构

详见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 协议

MIT License — 参见 [LICENSE](LICENSE)。

Copyright (c) 2026 子言·塔罗
