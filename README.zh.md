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
- **Agent 类型抽象** — 统一 `agent_types` 配置，支持 Hermes / OpenClaw / Cline / OpenCode / **Codex** / **Claude Code** 等 8 种运行时（见下方）
- **即插即用** — 不入侵 Agent 代码，CLI 是唯一契约

## 前置条件

- **Python ≥ 3.10**（核心运行环境）
- **各 Agent 的 CLI 工具**（Hermes / OpenClaw / OpenCode / Codex / Claude Code 等，按需安装）
- **API Key**（通过 `.env` 文件配置，见 `examples/config.example.json` 的说明）
- **AgentMemory**（可选增强层）— MCP 语义检索；**主记忆**为 `team-memory.db`（见下）
  - Docker 部署：`docker-agents/` 内 `iii-engine` + `agentmemory` 容器（端口 **3111**）
  - **禁止**在 Windows 计划任务中裸跑 AgentMemory；仅 WSL Docker 或 Linux 原生 Docker
  - 桥接: mailbus 双写 — 必写 SQLite，AgentMemory best-effort

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

# 4. 启动总线（推荐：内置 Scheduler，无需 crontab）
mailbus serve --host 0.0.0.0 --port 9814 --data-dir /path/to/your/store
# serve 启动后内置 SchedulerHub 自动跑 scan / memory_bridge / pipeline_watchdog 等 job

# 或手动扫描：
mailbus scan

# 5. 发消息
mailbus send agent-a --msg "你好，请处理这个任务" --from lingzhao
mailbus broadcast --msg "系统维护通知"

# 6. 查看状态
mailbus status
mailbus status --failed
```

## 跨平台部署

mailbus 是 **纯 Python + 文件系统**，在 **Linux / macOS 上可直接原生运行**，无需 WSL 或 Windows 专用桥接。默认 API 端口 **9814**（`lib/constants.py`）。

### 端口对照

| 部署方式 | API 端口 | 说明 |
|----------|----------|------|
| 原生 `mailbus serve` | **9814** | Linux / macOS / Windows 本机 |
| Docker `mailbus` 服务 | **9814** | `docker-agents/` compose 映射 `$MAILBUS_API_PORT`（默认 9814） |
| n8n webhook | **5678** | 可选；视频发布演练 |
| AgentMemory | **3111** | 可选 |
| 灵云 Claude ttyd | **9260** | WSL 宿主机 · Claude Code pro |
| 灵验 Claude ttyd | **9261** | WSL 宿主机 · Claude Code 测试 |

### 开发工程师 tier 派发（2026-06-25）

`role_type=8` 工单：**先按 model_tier 过滤候选人，再 least_load + 轮询**。

| tier | 派给谁 |
|------|--------|
| `pro`（需 `MAILBUS_ALLOW_PRO=1`） | 灵云 lingyun |
| `flash` / 默认 | 大力 dali、灵霄 lingxiao |

Envelope 示例：`constraints.dispatch.model_tier: "pro"`。离线 agent 自动 failover。详见 [`rules/model-routing.md`](rules/model-routing.md)。


同机 n8n / ComfyUI 直接用 `http://127.0.0.1:5678`、`8188`，**不需要** `wsl_bridge`。

```bash
# 1. 安装
git clone https://github.com/hopewang123456/ziyan-mailbus.git
cd ziyan-mailbus
python3 -m venv .venv && source .venv/bin/activate   # 可选
pip install -e .

# 2. 初始化
mailbus init --data-dir ./store
cp examples/config.example.json store/config.json   # 再编辑 agents / 密钥

# 3. 环境变量（项目根 .env，勿提交 git）
cat >> .env <<'EOF'
MAILBUS_API_TOKEN=你的密钥
GITHUB_TOKEN=ghp_...                    # 可选：platform-scout GitHub 源
N8N_PUBLISH_WEBHOOK_URL=http://127.0.0.1:5678/webhook/mailbus-multi-publish
EOF

# 4. 启动总线（内置 Scheduler：scan / platform-scout / pipeline-repair 等）
mailbus serve --host 127.0.0.1 --port 9814 --data-dir ./store
# 或后台重启：
python tools/restart-mailbus.py --port 9814

# 5. 可选：n8n 侧车
bash docker-agents/start-n8n.sh
bash tools/tools/ops/setup-n8n.sh

# 6. 验收
python3 tools/tools/ops/run-final-acceptance.py
python3 tools/validate-order-intake.py --data-dir store
# Dashboard：浏览器打开 docs/index.html（默认 API http://127.0.0.1:9814）
```

**systemd（可选）：** 见 `docker-agents/install-systemd.sh`、`docker-agents/docker-agents.service`。

### Windows（本机 Python + 可选 WSL Docker）

**mailbus 跑在 Windows、n8n 跑在 WSL Docker** 时，`localhost:5678` 可能不可达 — mailbus 会自动走 `lib/n8n/wsl_bridge.py`。

```powershell
pip install -e .
mailbus init --data-dir store
# 配置 .env（变量同 Linux）

python tools/restart-mailbus.py --port 9814
.\tools\tools/ops/setup-n8n.ps1            # 或 -Reset 重建 workflow 卷
# 或：wsl bash docker-agents/start-n8n.sh

python tools\tools/ops/run-final-acceptance.py
```

提示：可开 **WSL mirrored 网络** 或端口转发，减少对 WSL 桥接的依赖。Docker Desktop 全团队：`wsl bash docker-agents/start-team.sh`。

### Docker 全 Agent 团队

Hermes / OpenClaw / Codex / OpenCode 容器共享 `store/` 卷；Claude Code（灵云/灵验）跑在 WSL 宿主机 ttyd：

```bash
cd docker-agents
cp .env.example .env
bash start-team.sh
bash mailbus-pipeline-e2e.sh
```

Docker 与原生 mailbus API 均默认 **9814**（`docker-compose.yml` 与 `lib/constants.py`）。可通过环境变量 `MAILBUS_API_PORT` 覆盖；`docker-agents/lib/api-url.sh` 与 `config/env.template` 为启动链 SoT。

### 可选组件

| 组件 | 用途 | 安装 |
|------|------|------|
| **n8n** | 多渠道发布（video drill） | `tools/ops/setup-n8n.sh` / `tools/ops/setup-n8n.ps1` |
| **ComfyUI** | 生图步骤 | `docker-agents/start-comfyui-gpu.sh` |
| **AgentMemory** | 长期消息记忆 | `npm i -g @agentmemory/agentmemory && agentmemory` |

### 验收清单

```bash
python3 tests/run_all.py
python3 tools/validate-scheduler.py --url http://127.0.0.1:9814
python3 tools/tools/ops/smoke-platform-scout.py --data-dir store
python3 tools/validate-order-intake.py --data-dir store
python3 tools/tools/ops/run-final-acceptance.py
```

### 方案对照 — 仍待完善（见 `plans/`）

不阻塞 Linux 原生部署：

| 项 | 状态 |
|----|------|
| platform-scout → lingtuo task notify | ✅ `after_scout_notify_agent` |
| order-intake schema 校验脚本 | ✅ `tools/validate-order-intake.py` |
| 灵霄 auto-ack / chat `-q` 超时 | ✅ 文件任务推送 + phantom 检测 + CLI 超时重置 |
| Agent 权限持久化 | ✅ `permission.json` + API 规范化 |
| Token 统计 Dashboard | ✅ `/api/stats` token_estimates |
| 商前 role-flow（灵拓→灵昭） | ✅ role-flow.json pursue 转换 + intake 闸门 |
| 灵拓 Hermes profile 9126 | ✅ init-profiles.sh + config.json |
| Dashboard i18n 中英文 | ✅ `docs/js/dashboard-i18n.js` |
| 机器人 Agent 头像 | ✅ `docs/avatars/*.svg`（生成脚本已归档 `tools/_archive/gen-robot-avatars.py`） |

## 核心特性

| 特性 | 说明 |
|------|------|
| **零依赖** | 纯 Python + 文件系统，不需要 Redis / MQ / DB |
| **双向确认** | CLI 推送 → Agent 写 ack → 总线更新状态，不丢消息 |
| **消息协议** | type + action 结构化字段，Agent 不猜自然语言 |
| **任务追踪** | pending → running → success/failed/timeout，全链路追踪 |
| **优先级队列** | 加急消息优先推送，支持抢占 |
| **Agent 类型抽象** | 统一配置模板，内置 **8 种** Agent 运行时（见下方） |
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

`config.json` → `agents.<id>.type` 与 `agent_types` 模板一一对应；Adapter 实现见 [`lib/agent_adapters.py`](lib/agent_adapters.py)，L0/L1 Skill 见 [`adapters/README.md`](adapters/README.md)。

| 类型 | CLI 模板 | 框架 | 典型部署 |
|------|----------|------|----------|
| `hermes` | `hermes chat -q 'MSG' -Q` | Hermes Agent | Docker `hermes-base` |
| `hermes_profile` | `hermes chat -q 'MSG' -Q --profile PROFILE` | Hermes 多 Profile | Docker，端口 9120–9127 |
| `openclaw` | `openclaw agent --local --agent AGENT --message 'MSG'` | OpenClaw Gateway | Docker，端口 18789/18790 |
| `opencode` | `opencode run 'MSG' --dangerously-skip-permissions MODEL` | OpenCode CLI | Docker `dali` 或 WSL |
| `codex` | `codex exec 'MSG'`（`--json` + 文件任务） | OpenAI Codex CLI | Docker `codex-agent`（灵霄/灵鉴） |
| `claude_code` | `claude -p 'MSG'` | Claude Code CLI | **WSL 宿主机** ttyd（灵云 9260 / 灵验 9261） |
| `cline` | `cline 'MSG' PROVIDER --timeout 120` | Cline CLI（**legacy**） | 仅 WSL 直连；Docker 灵霄/灵鉴已迁 **codex** |
| `none` | 无 CLI | 纯文件通信 | 手动调度 / 外部触发 |

> **Cursor**（`adapters/cursor/`）为设计 stub，尚未接入 `agent_adapters` 推送链；复杂编码可走 Cursor 直连或见 [`docs/cursor-adapter-design.md`](docs/cursor-adapter-design.md)。  
> 扩展新框架：在 `agent_types` 增加 CLI 模板 + 可选 `BaseAdapter` 子类；Skill 规范见 [`adapters/README.md`](adapters/README.md)。

### 子言·AI 团队编制（12 人）

完整组织图见 [`ORGANIZATION.md`](ORGANIZATION.md)，机器可读表见 [`store/roles/json/roster.json`](store/roles/json/roster.json)。

| 域 | 成员 |
|----|------|
| 决策 | 灵昭（男） |
| 商前 | 灵犀（女）、灵拓（男）、一哥（男） |
| 交付 | 灵霄（男）、大力（男）、**灵云**（女）、灵瑾（女）、灵鉴（男）、**灵验**（女）、灵巡（男）、小七（女） |
| 商后 | 灵账（女） |

### 已注册 Agent 与框架（v2.1.0）

| Agent | 名称 | 职责 | 框架 |
|-------|------|------|------|
| `lingzhao` | 🪷 灵昭 | 方案设计 | Hermes |
| `lingjin` | 🦋 灵瑾 | 网络安全 | OpenClaw |
| `lingxi` | 🔭 灵犀 | 技术雷达 | Hermes Profile |
| `lingtuo` | 🧭 灵拓 | 市场拓展 | Hermes Profile |
| `lingjian` | 🔍 灵鉴 | 代码审查 | **Codex** |
| `lingyan` | 🧪 灵验 | 测试 QA | **Claude Code** |
| `lingxun` | 🔦 灵巡 | 巡检日报 | Hermes Profile |
| `lingzhang` | 🧾 灵账 | 账单催收 | Hermes Profile |
| `xiaoqi` | 🦞 小七 | 调度 | OpenClaw |
| `yige` | 👨‍🔧 一哥 | 运营内容 | OpenClaw |
| `lingxiao` | 🎯 灵霄 | 技术负责人（flash） | **Codex** |
| `dali` | 🤖 大力 | 编码（flash） | OpenCode |
| `lingyun` | ☁️ 灵云 | Pro 编码（Claude） | **Claude Code** |

> 💪 大壮（Aider 审查）已退役，由灵鉴 + review.py + Semgrep 替代。Cline 为 legacy，Docker 灵霄/灵鉴已迁 **Codex**。

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
mailbus serve [--host] [--port]      # 启动 HTTP API 服务（默认 127.0.0.1:9814）
mailbus launch                       # 启动所有 Agent 常驻进程（Gateway / Dashboard）
mailbus launch --status              # 查看 Agent 进程运行状态
mailbus launch --stop                # 停止所有 Agent 进程
mailbus launch --agent xiaoqi        # 启动指定 Agent
```

## Platform 管理界面

mailbus 自带一个独立 Web 管理界面 **ziyan-mailbus Platform**，零依赖，打开即用：

```bash
# 1. 启动 HTTP API
mailbus serve --host 127.0.0.1 --port 9814 --data-dir /path/to/store

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

## 记忆同步（双写：SQLite 主 + AgentMemory 辅）

mailbus 将已 ack 的消息**必写** [`team-memory.db`](/mnt/e/hermes-data/.hermes/shared-memory/team-memory.db)（与各 agent 启动脚本 `memory.py search` 共用），并 **best-effort** 同步到 [AgentMemory](https://github.com/rohitg00/agentmemory)（MCP 语义检索 / Codex hooks）。

内置 scheduler jobs：
- `memory_bridge`（默认每 120s）— 双写桥接
- `agentmemory_watchdog`（默认每 180s）— AM 连续不可达时 docker 重启

手动运行：

```bash
python3 mailbus-memory-bridge.py --data-dir /path/to/store
python3 /mnt/e/hermes-data/.hermes/scripts/memory.py search mailbus
python3 tools/tools/ops/check-agentmemory-persistence.py --dry-run   # 探针（加 --dry-run 跳过重启）
```

环境变量：

| 变量 | 默认 | 含义 |
|------|------|------|
| `MEMORY_BRIDGE_SQLITE` | `1` | 写 team-memory.db |
| `MEMORY_BRIDGE_AGENTMEMORY` | `1` | 写 AgentMemory |
| `TEAM_MEMORY_DB` | 见 compose | SQLite 路径 |

团队规范同步：`python3 tools/tools/ops/sync-team-rules.py --data-dir store`（bulletin + team-memory.db + 各 agent notice；AgentMemory 可选）

消息 SQLite 格式：`[agent:xxx] [from:yyy] [type:zzz] <内容>`，key=`mailbus:{msg_id}`

**运行约束**：AgentMemory 仅通过 WSL Docker（`docker-agents/start-team.sh`）运行；原生 Windows 不部署 AM，记忆走 SQLite + mailbus inbox 文件。

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

## 三轮迭代与回归（Docker 团队）

# Docker 团队部署（仓库内 docker-agents/）

配合仓库内 `docker-agents/` 编排使用时，可用以下脚本做端到端验证：

```bash
# 全流程：Round1 gate → Round2 → monitor 回归
bash docker-agents/mailbus-pipeline-e2e.sh

# 打怪升级小游戏 smoke
bash docker-agents/workflow-smoke.sh
python3 tools/run-game-lvup-e2e.py --task-id game-lvup-YYYYMMDD-HHMMSS --data-dir store

# 一键启动 Docker 团队（WSL）
bash docker-agents/start-team.sh
```

详见 `plans/mailbus-three-round-optimization.md` 与 `rules/iteration-protocol.md`。

## 项目结构

```
ziyan-mailbus/
├── bus.py                        # 入口脚本（CLI 命令入口）
├── docker-agents/start-team.sh    # 团队容器启动（推荐入口）
├── mailbus-send                   # 发送 CLI 包装
├── mailbus-memory-bridge.py       # AgentMemory 双写桥接
├── lib/
│   ├── scheduler.py              # 内置 SchedulerHub（替代 WSL crontab）
│   ├── jobs.py                   # scan / bridge / watchdog 等 job
│   ├── pipeline_trigger.py       # msg-results → 自动推进 pipeline
│   ├── iteration_engine.py       # 三轮迭代 Round1/2/3
│   ├── execution_orchestrator.py # 执行顺序 light 编排
│   ├── self_heal.py              # scan 前自愈
│   ├── scanner.py                # 扫描 inbox → 构建推送队列（P2 串行）
│   └── ...
├── docker-agents/                # Docker 团队部署（compose、start-team、e2e 脚本）
│   ├── docker-compose.yml
│   ├── start-team.sh / stop-team.sh
│   └── hermes-base/ openclaw-agent/ ...
├── tools/                        # 运维/回归脚本（e2e、triage、game-lvup 等）
├── rules/                        # 团队规范（init 时复制到 store/rules/）
├── mailbus-memory-bridge.py      # AgentMemory 桥接（可选）
├── store/                        # 运行时数据目录（gitignore，不提交）
├── plans/                        # 迭代方案与清单
├── tests/                        # 测试套件
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

无论你用的是 Hermes、OpenClaw、OpenCode、**Codex**、**Claude Code**、Cline（legacy）还是其他 AI Agent 框架——mailbus 都能让它们无缝对话。

欢迎各位大佬一起参与：
- **提 Issue** — 发现 bug、建议新功能
- **提交 PR** — 修复问题、扩展框架支持
- **分享案例** — 你是怎么用 mailbus 串联你的 Agent 团队的

## 协议

MIT License — 参见 [LICENSE](LICENSE)。

Copyright (c) 2026 子言·塔罗
