# mailbus

文件级 **Agent-to-Agent** 消息总线。不绑定单一框架：通过 Adapter 接入 Hermes / OpenClaw / Codex / OpenCode / Claude Code 等。

无需 Redis / RabbitMQ —— 消息存 JSON，CLI 推送，Agent 回 ack。

## 环境

- Python ≥ 3.10
- 可选：Docker、Ollama（本机路由）、AgentMemory
- 至少一个 Agent CLI 或 A2A 端点

## 快速开始

```bash
git clone https://github.com/hopewang123456/mailbus.git
cd mailbus
pip install -e .

mailbus init --data-dir ./store
mailbus serve --host 0.0.0.0 --port 9814 --data-dir ./store

mailbus send agent-a --msg "你好" --from agent-b --data-dir ./store
mailbus status --data-dir ./store
```

将 [`migrate/env.template`](migrate/env.template) 复制为 `.env` 并填写密钥/路径。**不要提交 `.env`。**

### LLM / Ollama

首次启动优先使用本机 Ollama（未配置时取 Ollama 列表中的第一个模型）。  
若既无 Ollama 也无云端 API Key，驾驶舱会提示配置。

### 公共 Docker（最小栈）

```bash
cd docker-agents
docker compose -f compose.public.yml up -d --build
```

完整本地团队栈请继续用 `docker-compose.yml` + 本机 `docker-compose.override.yml`（不入库）。

### 团队栈日启（Linux / macOS / Windows）

规范入口（Linux/macOS **不需要** PowerShell）：

```bash
python tools/mailbus.py doctor
python tools/mailbus.py start
python tools/mailbus.py docker restart-mailbus
```

#### 部署差异

| | **Linux / macOS 原生** | **Windows + WSL 团队栈** |
|--|------------------------|--------------------------|
| 日启 | `python tools/mailbus.py start` 或 `mailbus serve` | 同一 Python 入口；可用 `scripts/`、`tools/mailbus/` 下薄 `.bat` |
| 浏览器访问 API | 直接打开 `http://127.0.0.1:9814/` | 服务在 **WSL 内**、浏览器在 **Windows** 时，WSL IP / `wslrelay` 过期会导致 localhost 不通 |
| 端口转发 | **不需要**（`portproxy` 为空操作） | `python tools/mailbus.py portproxy` 或 `windows/fix-wsl-localhost.ps1`（可能 UAC）。见 [`windows/README.md`](windows/README.md) |
| Ollama | 本机 Ollama / `MAILBUS_OLLAMA_URL` | Windows 宿主机 Ollama + 可选 WSL 代理（仅 win32/wsl 启动路径） |

Windows 专用端口转发脚本统一放在 [`windows/`](windows/)。

#### 外部扩展（框架 / 集成）

启动时发现（**无热加载**）：

| 类型 | config | 环境变量 | pkg entry-points |
|------|--------|----------|------------------|
| 框架 Adapter | `frameworks.plugins` | `MAILBUS_FRAMEWORK_PLUGINS` | `mailbus.frameworks` |
| Integrations | `integrations.plugins` | `MAILBUS_INTEGRATION_PLUGINS` | `mailbus.integrations` |

规格：`module` 或 `module:callable`（callable 内调用 `register_framework` / `register_integration`）。严格失败：`*_PLUGINS_STRICT=1`。

## 敏感数据与私有配置

**不要把密钥或个人 Agent 名册提交进 Git。** 正式敏感/个人文件留本机；仓库只放 example。

| 本机保留（已忽略） | 公开示例 |
|--------------------|----------|
| `.env`、`store/secrets.json`、`store/` | [`migrate/env.template`](migrate/env.template)、[`docker-agents/.env.example`](docker-agents/.env.example) |
| `access/transport/<你的agent>/` | [`examples/transport/`](examples/transport/)（`agent-a` / `agent-coder` / `agent-chat`） |
| `config/agents/<id>.override.json` | [`config/agents/*.override.example.json`](config/agents/) |
| `config/mailbus/launch-ports.json` | [`launch-ports.example.json`](config/mailbus/launch-ports.example.json) |
| `access/external-tools/registry.json`、`grants.json` | `*.example.json` |
| compose override、Comfy 本机挂载 | `*.override.example.yml` |

**运行时只读不带 `.example` 的实文件。** Clone 后：复制 `foo.example.json` → `foo.json`，填自己的密钥与 Agent id。详见 [`config/README.md`](config/README.md)。

无敏感的公共种子（pipeline、agent-types 等）可直接以普通 JSON 提交。

## 使用

### 常用 CLI

| 命令 | 作用 |
|------|------|
| `mailbus init --data-dir ./store` | （重建）`store/config.json`（seed + 本机覆盖合并） |
| `mailbus serve --host 0.0.0.0 --port 9814` | HTTP API + 内置调度器 + 驾驶舱 |
| `mailbus send <agent-id> --msg "..." --from <agent-id>` | 推送消息到 Agent 收件箱 |
| `mailbus broadcast --msg "..."` | 发布公告板 |
| `mailbus ack <msg-id> --agent <agent-id>` | 确认收到（驱动重试/退避） |
| `mailbus scan --data-dir ./store` | 扫描收件箱并派发待处理消息 |
| `mailbus status --data-dir ./store` | 查看 Agents / 队列 / 未读 |
| `mailbus search --data-dir ./store --query ...` | 消息 / 目录检索 |
| `mailbus agent-add <agent-id> --type <framework>` | 注册 Agent |
| `mailbus launch <agent-id> --kind browser` | 启停 Agent 常驻进程 |
| `mailbus review / recover / iteration` | 代码审查 / 任务 recover / 三轮迭代 |
| `mailbus backup --data-dir ./store` | 备份 store |

每个命令可用 `mailbus <cmd> --help` 查看选项。

### 驾驶舱（Web UI）

`mailbus serve` 后打开 `http://127.0.0.1:9814/`：

- **舰队 / 收件箱** —— Agent 实时状态、未读、发送与 ack
- **任务** —— pipeline / FSM 状态、指派、审计（`?reviewer=`）、recover
- **设置** —— **智能体配置**与**模型配置**已表单化编辑：每个字段直接表单输入，保存后仍以 JSON 落盘；`frameworks / mailbus_codex / mailbus_claude` 保留 JSON 折叠编辑器
- **设置 / 资产路径** —— skill / rule / identity 三项根目录单选「默认 / 自定义」：默认走仓库内 junction 路径（`skills/` `rules/` `identities/`，SoT 在 Obsidian Vault）；自定义写 `.env`（`MAILBUS_SKILLS_ROOT` / `MAILBUS_RULES_ROOT` / `MAILBUS_IDENTITIES_ROOT`），需重启生效
- **门诊 / doctor** —— 一键健康检查（Hermes 就绪、compose 漂移、token 预算等）

### 发一条 A2A 消息

```bash
# agent-b 请 agent-a 评审 order-intake 流程
mailbus send agent-a --msg "请评审 order-intake 流程" --from agent-b --data-dir ./store

# 调度器扫到后查看状态
mailbus status --data-dir ./store
mailbus search --data-dir ./store --query order-intake
```

## 配置指南

### 配置入口一览

| 文件 | 作用 | 提交策略 |
|------|------|----------|
| `store/config.json` | 主配置：项目信息、`agents` 注册、`agent_types`、`smart_routing`、`org_defaults` 等 | gitignored（`mailbus init` 从 seed 生成） |
| `config/agents/<id>.override.json` | 单 agent 覆盖：模型、launch 模板、超时 | 本机文件（提交 `<id>.override.example.json`） |
| `config/mailbus/launch-ports.json` | agent id → 浏览器/API 端口映射 | 本机文件（提交 example） |
| `access/transport/<id>/transport.json` | agent 的 transport 注册（框架、路径、可达性） | 本机文件（提交到 `examples/transport/`） |
| `config/mailbus/agent-types.json` | 框架 push 命令模板 + 模型 CLI 参数 + launch 模板 | 可直接提交 |
| `config/mailbus/base.json` | 公共 seed（ack/retry/archive 阈值、`org_defaults` demo 名册） | 可直接提交 |
| `config/mailbus/compose-registry.json` | 逻辑 build 名 / agent id → docker-compose 服务名 | 可直接提交 |
| `config/mailbus/role-types.json` | 角色类型 → 候选 agent（demo） | 可直接提交 |
| `.env` | API keys / 路径 | **绝不提交**（用 `migrate/env.template`） |

### `store/config.json` 的 `agents` 对象

`agents` 是 `agent_id → 配置` 的映射，运行时校验见 `lib/adapters/config/config_schema.py`：

```json
"agents": {
  "agent-a": {
    "name": "Agent A",
    "role": "设计",
    "type": "hermes",
    "models": ["deepseek-chat"],
    "inbox": "/path/to/store/inbox/agent-a/inbox.json",
    "profile_paths": {
      "identity": "/path/to/agent-a/IDENTITY.md",
      "soul": "/path/to/agent-a/SOUL.md",
      "skills_dirs": ["/path/to/skills/"],
      "memory_dir": "/path/to/memory/"
    }
  }
}
```

常用字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | **必填**，枚举：`hermes`、`hermes_profile`、`openclaw`、`opencode`、`codex`、`claude_code`、`cline`、`none` |
| `name` / `role` | string | 显示名 / 职责（驾驶舱展示用） |
| `models` | string[] | 模型名列表，需在 `agent_types.models` 中定义对应的 CLI 参数 |
| `enabled` | bool | 是否启用该 agent |
| `max_concurrency` | int | 并发上限（默认 1） |
| `inbox` | string | 收件箱 JSON 路径 |
| `profile_paths` | object | `identity` / `soul`（人设文件）、`skills_dirs`、`memory_dir` |
| `webhook_url` / `webhook_secret` | string | 可选：消息推送 Webhook |
| `launch` | object | 启动偏好（见下） |

### 单 agent 覆盖：`config/agents/<id>.override.json`

个人化配置不进 `store/config.json`，用 override 覆盖（不涉及 secrets，只放 launch/UI 偏好）：

```json
{
  "models": ["deepseek-flash"],
  "launch": {
    "template": "claude_host",
    "launch_via_api": true,
    "has_browser": true,
    "browser": { "kind": "claude_ttyd", "url": "http://127.0.0.1:{port}/", "web_port": "9260" }
  },
  "push_timeout_seconds": 900
}
```

`launch.template` 引用 `config/mailbus/agent-types.json` 里的 `launch_templates`（如 `claude_host`、`codex_docker`、`hermes_dashboard`、`openclaw_gateway`、`opencode_cli`）。

### 注册一个新 agent（完整流程）

1. 建 `access/transport/<your-id>/transport.json`（可复制 `examples/transport/agent-coder/transport.json` 改路径）。
2. 建 `config/agents/<your-id>.override.json`（复制 `coder.override.example.json`）。
3. 在 `config/mailbus/launch-ports.json` 给 `<your-id>` 映射端口（复制 `launch-ports.example.json`）。
4. 在 `store/config.json` 的 `agents` 里登记 `<your-id>`（参考 `examples/config.example.json`）。
5. 重跑 `mailbus init --merge --data-dir ./store`（或启动时自动发现），再到驾驶舱 **设置** 页确认/启用。

### 模型与 push 命令

`config/mailbus/agent-types.json` 的 `models` 定义每个模型对每个框架的 CLI 参数（例如 `deepseek-flash` → `opencode: --model deepseek/deepseek-chat`）。框架 `push` 命令模板（`hermes chat …`、`claude -p 'MSG'` 等）在同一文件顶层；`type: "none"` 表示纯文件通信、无 CLI 推送。

### 实例 / 角色装配语义（skills / rules / 人设）

配置页分两层：**实例卡**（框架级）与**角色卡**（个人级）。同一角色最终加载的内容按固定公式装配（实现见 `lib/adapters/config/assemble.py`）：

| 维度 | 公式 | 冲突规则 |
|------|------|----------|
| **skills** | 角色私有 ∪ 技能组（`skill_groups[]` 多选）∪ 框架公共 | 同名覆盖：**角色 > 组 > 框架** |
| **rules** | 框架 rules + 个人 rules | **框架优先**，永远排在个人前；**无**共享组 |
| **人设** | 框架自动扫描（`SOUL.md`/`CLAUDE.md`/`AGENTS.md`）∪ 用户添加（`persona_files[]`） | 保存用户添加时 **V1** 校验路径存在，缺失提示「可能无法沟通」（V2 探活 → 诊所 backlog） |

要点：

- **实例层自定义 = 该框架实例下全员公共**；**角色层 = 仅自己 + 可选组**。私有不能关掉框架公共。
- **skillgroup**：根下每个**一级子目录 = 一个组**，跨框架可复用。默认根为仓库 `skills/skillgroup/`（开箱）；本机 SoT 在 Obsidian Vault，可用 `MAILBUS_SKILLGROUP_ROOT` 指过去（如 `03-shared/skillgroup`），避免双源。
- 角色卡多选组存到 `store/config.json` 的 `agents.<id>.skill_groups[]`；人设额外文件存 `agents.<id>.persona_files[]`。

**运行环境字段的 SoT 在实例卡**（不在角色卡）：`run_target` / `install_path` / `host` / `custom_paths` / `distro` 由实例卡唯一持有，角色卡只读继承（`instance_id` 指针），不再双写。`type` / `run_target` 决定「框架跑在哪」；同一框架可多端多实例（如 `hermes@docker` 与 `hermes@wsl@ubuntu` 各建一个实例、各自加载角色）。

**enabled 双层级**：

- 角色级 `enabled` = 员工「退役 / 工作」（下线不删除，除非在框架实例配置里彻底删）。
- 实例级 `enabled` = 该容器是否继续监测；关闭后该实例下所有角色下架。
- 扫描验证（`/api/agents/scan`）写回实例级 `install_path/run_target/distro/gate_passed`，不覆盖角色级 `enabled`。mailbus 不改变 agent 框架自身配置，只做配置读取与通信桥接。

### 默认角色指派（org_defaults）

`store/config.json` 的 `org_defaults` 段定义各内置角色的默认 agent（reviewer / escalate / notify / scheduler / audit_reviewers 等）。开源 seed 用 demo id，见 `config/mailbus/base.json`：

```json
"org_defaults": {
  "reviewer": "agent-a",
  "notify_agents": ["agent-a", "agent-m"],
  "scheduler": "agent-b",
  "audit_reviewers": ["agent-a", "agent-f"]
}
```

## Demo Agent

公开示例使用通用 id：`agent-a` / `agent-b` / `agent-c`。  
见 [`examples/demo-roster.json`](examples/demo-roster.json)。

在驾驶舱 **配置中心** 注册自己的 Agent；自动发现后默认 **不启用**，需手动 enable。

## 驾驶舱

`mailbus serve` 后打开 `http://127.0.0.1:9814/`。旧版 UI：`/legacy`。

## 架构

Ports & Adapters 分层（详见 [`ARCHITECTURE.md`](ARCHITECTURE.md) 与 [`AGENTS.md`](AGENTS.md)）：

```
tools/ · lib/api/ → lib/application/ → lib/interfaces/ ← lib/adapters/
                         ↓
               lib/domain/ · lib/core/
                         ↓
                    lib/infra/
```

| 层 | 职责 |
|----|------|
| `lib/interfaces/` | Protocol 接口（原 `ports`） |
| `lib/core/a2a/` | A2A 核心协议（原 `lib/transport`） |
| `lib/application/` | 用例（workflow、harness、scan、push、orchestration 等） |
| `lib/adapters/` | frameworks、plane、config（`CompositeConfigRepo`）、transport、container（`resolver.py`）等 |
| `lib/infra/` | clock、路径、`mbus_log`、internal LLM 启动 |

唯一 Composition Root：`lib/composition.py`（`build_a2a_transport`、`build_transport_bundle`、`build_config_repo` 等）。  
各包有 `Overview.md` 目录地图。路径迁移：[`docs/migration-guide.md`](docs/migration-guide.md)。  
Harness 规则：`config.harness.rules_path`；链路模板：`config/mailbus/chains.template.json`。

## 文档

- 架构：[`ARCHITECTURE.md`](ARCHITECTURE.md)
- Agent 入口：[`AGENTS.md`](AGENTS.md)
- 迁移指南：[`docs/migration-guide.md`](docs/migration-guide.md)
- 遗留 bash 评估：[`docs/legacy-bash-eval.md`](docs/legacy-bash-eval.md)
- Adapter：[`docs/agent-adapter-layer.md`](docs/agent-adapter-layer.md)
- Harness：[`docs/harness-runtime-spec.md`](docs/harness-runtime-spec.md)
- 环境变量模板：`migrate/env.template`

## 许可证

MIT
