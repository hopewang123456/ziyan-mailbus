# ziyan-mailbus

文件级 **Agent-to-Agent** 消息总线。不绑定单一框架：通过 Adapter 接入 Hermes / OpenClaw / Codex / OpenCode / Claude Code 等。

无需 Redis / RabbitMQ —— 消息存 JSON，CLI 推送，Agent 回 ack。

## 环境

- Python ≥ 3.10
- 可选：Docker、Ollama（本机路由）、AgentMemory
- 至少一个 Agent CLI 或 A2A 端点

## 快速开始

```bash
git clone https://github.com/hopewang123456/ziyan-mailbus.git
cd ziyan-mailbus
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
