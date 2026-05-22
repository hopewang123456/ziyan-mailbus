# ziyan-mailbus

**打破 Agent 之间的交互壁垒，实现真正的 A2A（Agent-to-Agent）通信。**

ziyan-mailbus 是一个独立、解耦、轻量的**文件级消息中间件**，专为多 Agent 团队设计。不依赖任何 Agent 框架，不入侵 Agent 代码——CLI 是唯一契约，即插即用。

> 不需要 Redis / RabbitMQ / 数据库。消息存 JSON 文件，CLI 推送，Agent 即时回复 ack。

## 设计哲学

- **真正的 A2A** — 让不同框架的 Agent 之间可以自由通信，不绑定任何特定的 Agent 实现
- **文件即通信** — 消息存 JSON 文件，零中间件依赖。备份=cp，迁移=scp
- **双向确认** — CLI 推送 + Agent 主动 ack，不搞"推送即送达"的幻觉
- **先队列再推送** — 加急排队优先，普通排队顺序，同 Agent 批量推送
- **故障隔离** — 推送失败 3 次 → 写错误日志 → 监控 Agent 扫日志找修复方案
- **Agent 类型抽象** — 统一 `agent_types` 配置，支持 Hermes / OpenClaw / Cline / OpenCode 等框架
- **即插即用** — 不入侵 Agent 代码，CLI 是唯一契约

## 前置条件

- **Python ≥ 3.10**（核心运行环境）
- **各 Agent 的 CLI 工具**（Hermes / OpenClaw / Cline / OpenCode 等，按需安装）
- **API Key**（通过 `.env` 文件配置，见 `examples/config.example.json` 的说明）
- **AgentMemory**（可选）— 用于消息持久化记忆，确保 Agent 重启后能检索历史消息
  - 安装: `npm install -g @agentmemory/agentmemory`
  - 启动: `agentmemory`（默认监听 http://localhost:3111）
  - 桥接: mailbus 自动将已 ack 的消息同步到 AgentMemory

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
| **双向确认** | CLI 推送 → Agent 写 ack → 总线更新状态，不丢消息 |
| **消息协议** | type + action 结构化字段，Agent 不猜自然语言 |
| **任务追踪** | pending → running → success/failed/timeout，全链路追踪 |
| **优先级队列** | 加急消息优先推送，支持抢占 |
| **Agent 类型抽象** | 统一配置模板，支持 6 种 Agent 框架（见下方） |
| **多模型 Fallback** | 模型别名系统，按顺序试，不通自动换下一个 |
| **公告板** | `broadcast` 一键全员推送 |
| **催办** | 超时自动重推 + 升级通知 |
| **心跳检测** | 定时 ping Agent，离线不进重试 |
| **消息检索** | SQLite FTS5 全文索引 |
| **错误回执** | 标准化 error_code/reason/trace |
| **错误日志** | 推送失败写 JSONL 日志，按周分文件 |
| **记忆同步** | 可选桥接 AgentMemory，消息自动持久化 |
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

> 新增框架只需在 `agent_types` 加一条 CLI 模板，代码零改动。

## CLI 命令总览

```bash
mailbus init                        # 初始化目录结构
mailbus scan                        # 扫描全员 inbox → 推送 + 心跳 + 催办 + 索引
mailbus send <agent>                # 手动发消息（--priority/--type/--forward-to）
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
mailbus heartbeat                   # 心跳检测（检测所有 Agent 在线状态）
mailbus search                      # 消息全文检索（--query/--from/--to/--type/--status）
mailbus serve [--port]              # 启动 HTTP API 服务（默认端口 9812）
```

## Platform 管理界面

mailbus 自带一个独立 Web 管理界面 **ziyan-mailbus Platform**，零依赖，打开即用：

```bash
# 1. 启动 HTTP API
mailbus serve --port 9812 --data-dir /path/to/store

# 2. 浏览器打开 docs/platform.html（或用任意静态服务器托管）
#    页面自动从 API 加载数据
```

**功能：**

| 区域 | 内容 |
|------|------|
| **概览** | Agent 数量、消息总数、待处理数 |
| **Agent 列表** | 名称、类型、角色、模型配置（动态读取 config.json） |
| **任务追踪** | 状态、追踪链、催办次数 |
| **心跳状态** | AgentMemory / 磁盘 / inbox 积压 / 各 Agent 在线状态 |
| **告警历史** | 级别、类型、时间 |
| **原始 JSON** | 各 API 端点的原始数据查看 |

**操作：**
- 🔄 **刷新全部** — 重新加载所有数据
- 💓 **触发心跳检测** — 手动跑一轮 Agent 在线检测
- 各区域独立 **🔄 刷新** — 单独刷新某个区块，不用全部重载
- **自动刷新** — 在 `config.json` 设置 `dashboard_refresh_seconds`（如 15 秒），平台自动定时刷新

Platform 完全独立于 Agent 框架，迁移到其他环境只需改 API 地址即可使用。

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

完整的配置示例见 [examples/config.example.json](examples/config.example.json)。

```json
{
  "project": "ziyan-mailbus",
  "version": "1.0.0",
  "data_dir": "/path/to/your/store",
  "ack_timeout": 30,
  "max_retries": 3,
  "archive_days": 7,
  "archive_max_messages": 300,
  "dashboard_refresh_seconds": 15,
  "agents": {
    "agent-a": {
      "name": "Agent A",
      "role": "描述",
      "type": "hermes",
      "models": ["deepseek-chat"],
      "inbox": "/path/to/your/store/inbox/agent-a/inbox.json"
    }
  },
  "agent_types": {
    "hermes": {
      "push": "hermes chat -q 'MSG' -Q",
      "description": "Hermes Agent 实例"
    },
    "models": {
      "deepseek-chat": {
        "opencode": "--model deepseek/deepseek-chat",
        "cline": "--provider openai-compatible"
      }
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
│   ├── models.py                 # 数据模型（Message / Inbox / MsgType）
│   ├── scanner.py                # 扫描 inbox → 构建推送队列
│   ├── pusher.py                 # CLI 推送 + 多模型 fallback
│   ├── ack_handler.py            # 处理 Agent 回复（ack / mark_read / forward）
│   ├── archiver.py               # 已读消息归档
│   ├── tracker.py                # 任务追踪 + 催办
│   ├── heartbeat.py              # 心跳检测 + 健康监控
│   ├── search.py                 # SQLite FTS5 全文检索
│   ├── alerter.py                # 告警系统
│   ├── api_server.py             # HTTP API 服务
│   └── utils.py                  # 文件锁、JSON 读写、消息构建
├── mailbus-memory-bridge.py      # AgentMemory 桥接（可选）
├── store/                        # 运行时数据目录（gitignore，不提交）
├── tests/                        # 测试套件（10 文件，90+ 用例）
├── docs/
│   ├── platform.html             # Web 管理界面（独立 HTML，零依赖）
│   ├── architecture-v2.html      # 架构图
│   ├── quickstart.md
│   └── message-format.md
├── examples/
│   └── config.example.json       # 示例配置（不含私有信息）
├── ARCHITECTURE.md
├── README.md
├── CHANGELOG.md
├── LICENSE
└── pyproject.toml
```

## 架构

详见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 欢迎共建

ziyan-mailbus 的目标是实现真正的 **A2A（Agent-to-Agent）** 通信，打破不同 Agent 框架之间的交互壁垒。

无论你用的是 Hermes、OpenClaw、Cline、OpenCode、Aider 还是其他 AI Agent 框架——mailbus 都能让它们无缝对话。

欢迎各位大佬一起参与：
- **提 Issue** — 发现 bug、建议新功能
- **提交 PR** — 修复问题、扩展框架支持
- **分享案例** — 你是怎么用 mailbus 串联你的 Agent 团队的

## 协议

MIT License — 参见 [LICENSE](LICENSE)。

Copyright (c) 2026 子言·塔罗
