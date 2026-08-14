# Mailbus Architecture（Ports & Adapters）

> Layer: docs · Owner: mailbus maintainers · local_root: `<repo-root>`
> Deep cleanup SoT: Cursor plan `mailbus-arch-deep-cleanup`（勿在执行中改 plan 文件）

## Dependency rule

```
tools/ · lib/api/  →  lib/application/  →  lib/interfaces/  ←  lib/adapters/
                              ↓
                    lib/domain/ · lib/core/
                              ↓
                         lib/infra/   (cross-cutting only)
```

- `application` MUST NOT import `adapters.frameworks.*` concrete modules (use ports / composition bind).
- `adapters` MUST NOT import `application`.
- `domain` MUST NOT import application / adapters / api.
- `composition.py` is the **only** Composition Root.
- Prefer package `Overview.md` files as in-tree maps.

## 网络模型（跨环境接入）

### 四环境拓扑与 run_target 分发

Agent 的 `run_target`（`windows|wsl|linux|docker`）经 `lib/adapters/runtime` **分发器**选适配器（Path 口已落地；Probe/Launch/Cred 后续）。  
**WSL 按 Ubuntu**；Linux DistroProfile 区分 Ubuntu / CentOS 族。Windows↔WSL 可作为跨边界测试床（≠真局域网交付）。

Mailbus **进程**所在端仍由 `lib/infra/runtime_net.py` 的 `runtime_env()` 探测，与 agent `run_target` 分开。

### 实例 / 角色 SoT 分层

- **实例卡（`agent_instances`）** = 框架运行环境唯一 SoT：`type` / `run_target` / `install_path` / `host` / `custom_paths` / `distro` / `enabled`（容器是否监测）/ `gate_passed`。
- **角色卡（`agents`）** = 员工个体：`name` / `role` / `models` / `provider` / `max_concurrency` / `enabled`（退役/工作）/ `paths`（私有资产）/ `skill_groups` / `persona_files` / `launch` / `port`；仅留 `instance_id` 指针，运行时只读继承实例。
- **三级启用门禁**（`lib/application/lifecycle.py::list_active_agents`）：角色 `enabled` → 实例 `enabled`（disabled 则该实例下所有角色下架，不删除）→ 框架 registry `enabled`。
- **`distro`**（`auto|ubuntu|centos`）仅对 `wsl/linux` 有意义（Ubuntu/CentOS 命令不同）；同一框架可多端多实例（如 `hermes@docker` 与 `hermes@wsl@ubuntu` 各建一个实例、各自加载角色）。
- **扫描门禁**（`/api/agents/scan`）写回**实例级** `install_path/run_target/distro/gate_passed`，不覆盖角色级 `enabled`。
- **mailbus 不改变 agent 框架自身配置**（profiles / SOUL.md 等），只做框架配置读取与通信桥接。

### 四环境拓扑

```
Host (Windows / WSL / Linux native)            Docker daemon
┌────────────────────────────┐               ┌──────────────────────────────┐
│  mailbus 进程 (9814)        │               │  hermes 9120-9127             │
│  浏览器                     │  ports 发布    │  codex 9220/9240/9250         │
└────────────────────────────┘ ──────────────▶│  openclaw 18789/18790         │
                                             │  claude ttyd 9260             │
                                             └──────────────────────────────┘
```

- **浏览器 + mailbus 同边**时 `127.0.0.1` 即可（`docker-compose.yml` 已把 agent 端口 + 9814 发布到 host localhost，且配了 `extra_hosts: host.docker.internal:host-gateway`）。
- 只有 **mailbus 跑在容器内**才需 `host.docker.internal`。
- 环境探测收敛到 `lib/infra/runtime_net.py`：`runtime_env()` → `windows|wsl|linux|docker`；`browser_host()` → 白名单 IP > `host.docker.internal`(docker) > `127.0.0.1`。

### 白名单语义

- `browser_hosts` 来源：`store/config.json` 顶层数组 < `MAILBUS_BROWSER_HOSTS` env（覆盖）。
- 空 = 仅本机 `127.0.0.1`（现状零变化）。
- **白名单只决定「生成的 URL 用什么 host」+「逐 agent 鉴权门槛」**；真正端口放行仍由 compose 端口发布、`serve --host`、agent 浏览器鉴权、反代/防火墙共同承担。

### 浏览器入口鉴权清单

| 入口 | 端口 | 鉴权 | 免密路径 |
|------|------|------|----------|
| Hermes dashboard | 9120-9127 | 固定 session token | mailbus 生成固定 `HERMES_DASHBOARD_SESSION_TOKEN` 存 `store/secrets.json` 注入容器（跨重启不变） |
| Codex Web UI | 9220/9240 | password + `codex_web_local_token` cookie | 注入 `CODEX_UI_PASSWORD` + `CODEX_HOME` 卷持久化 |
| Codex ttyd | 9250 | ttyd Basic Auth `-c` | 自生成 `browser_auth.<agent>` → `-c` + URL userinfo |
| Claude ttyd | 9260 | ttyd Basic Auth `-c` | 自生成 `browser_auth.<agent>` → `-c` + URL userinfo |
| OpenClaw | 18789/18790 | `--auth token` | 读 env / `openclaw.json` / auth 块 → `?token=` |
| OpenCode | 无 | 纯 CLI | 排除；LLM key 归容器内 |

- auth 块统一注入组件：`lib/adapters/config/browser_auth.py`（`resolve_agent_auth` / `build_authed_url` / `agent_browser_authed`）。
- **LLM provider 鉴权不归 mailbus**（cc-switch / DeepSeek 中转 key 是 agent 内部配置）。
- **「免密」= 卡片/secrets 已收口凭据**（鉴权仍属 agent）；机制按框架可为 URL 注入、env、或首次输入后浏览器记住；过期需重登。

### 广域网安全边界

- 无浏览器凭据的 agent 非本机 host 下 URL 生成退回 `127.0.0.1`。
- Basic Auth userinfo 会进 URL 历史，公网必须 HTTPS 反代。
- 广域网强制有效 token（非 `change-me`）。
- 本机默认行为零变化：空白名单 = `127.0.0.1`，四环境探测与现状一致。

## Package map

| Package | Role |
|---------|------|
| `lib/interfaces/` | Protocol interfaces (ex-`ports`); e.g. `ConfigRepository`, `MessageTransportPort`, `A2ATransportPort`, `LocalePort` |
| `lib/domain/` | DTOs, models, FSM primitives |
| `lib/core/a2a/` | A2A protocol types + routing (ex-`lib/transport`) |
| `lib/application/` | Use cases: workflow, harness, scan, push, internal_llm, ops, orchestration |
| `lib/adapters/` | frameworks, plane, config, transport, container, locale, integrations, ops, fakes |
| `lib/infra/` | clock, path root, `mbus_log`, internal_llm ensure/startup |
| `lib/api/` | Thin HTTP handlers |

Notable adapter modules:

- `lib/adapters/container/resolver.py` — `MAILBUS_CONTAINER_PREFIX` / per-service container name resolution
- `lib/adapters/config/composite_config.py` — `CompositeConfigRepo` (MD agents win over JSON)
- `lib/adapters/transport/http_a2a.py` — production `A2ATransportPort` (bound via `build_a2a_transport` / `build_transport_bundle`)

## Agent roster（智能体员工花名册）

| 代号 | 名称 | 框架 | 版本 | 浏览器 | 终端 | 身份文件 |
|------|------|------|------|--------|------|---------|
| 代号 | 名称 | 框架 | 版本 | 浏览器 | 终端 | 身份文件 |
|------|------|------|------|--------|------|---------|
| `agent-a` | Agent A | Hermes · dashboard | hermes-agent 0.17.0 | `:9120` (免登) | `docker exec hermes chat` | `profiles/agent-a/SOUL.md` |
| `agent-c` | Agent C | Hermes · dashboard | hermes-agent 0.17.0 | `:9121` (免登) | `docker exec hermes chat` | `profiles/agent-c/SOUL.md` |
| `agent-d` | Agent D | Hermes · dashboard | hermes-agent 0.17.0 | `:9122` (免登) | `docker exec hermes chat` | `profiles/agent-d/SOUL.md` |
| `agent-l` | Agent L | Hermes · dashboard | hermes-agent 0.17.0 | `:9125` (免登) | `docker exec hermes chat` | `profiles/agent-l/SOUL.md` |
| `agent-j` | Agent J | Hermes · dashboard | hermes-agent 0.17.0 | `:9126` (免登) | `docker exec hermes chat` | `profiles/agent-j/SOUL.md` |
| `agent-k` | Agent K | Hermes · dashboard | hermes-agent 0.17.0 | `:9127` (免登) | `docker exec hermes chat` | `profiles/agent-k/SOUL.md` |
| `agent-h` | Agent H | Claude Code (host) | 2.1.226 | — | `claude --project` (WSL) | `.mailbus/claude/agent-h/` |
| `agent-f` | Agent F | Claude Code (host) | 2.1.226 | — | `claude --project` (WSL) | `.mailbus/claude/agent-f/` |
| `agent-g` | Agent G | Codex · Docker | codex-cli 0.147.0 | `:9240` (Web UI) | `docker exec codex` | Codex identity preset |
| `agent-e` | Agent E | Codex · Docker | codex-cli 0.147.0 | `:9241` (Web UI) | `docker exec codex` | Codex identity preset |
| `agent-i` | Agent I | OpenCode · Docker | opencode 1.18.16 | — | `docker exec opencode cli` | — |
| `agent-m` | Agent M | OpenClaw · Docker | 2026.7.1-2 | `:18789/chat?token=change-me` | `docker exec openclaw tui` | `/workspace/SOUL.md` |
| `agent-n` | Agent N | OpenClaw · Docker | 2026.7.1-2 | `:18790/chat?token=change-me` | `docker exec openclaw tui` | `/workspace/IDENTITY.md` |

> 说明：上表为**示例名册**（demo ids）。实际 roster 以 `store/config.json` 的 `agents` 段为准（`mailbus init-store` 聚合 `config/mailbus/` 与本地覆盖生成）。

### 集成工具

| 工具 | 版本 | 端口 | 说明 |
|------|------|------|------|
| n8n | 1.76.1 | `:5678` | 独立 compose 栈，可视化 workflow 编排 |
| AgentMemory | iii-engine | `:3111` | 共享记忆存储 |

### Agent Memory 连接状态

| Agent | 框架 | AgentMemory 连接 | 身份文件 |
|-------|------|-----------------|---------|
| Agent | 框架 | AgentMemory 连接 | 身份文件 |
|-------|------|-----------------|---------|
| agent-a | Hermes | ✅ `AGENTMEMORY_URL` (compose) | `profiles/agent-a/SOUL.md` |
| agent-c | Hermes | ✅ `AGENTMEMORY_URL` (compose) | `profiles/agent-c/SOUL.md` |
| agent-d | Hermes | ✅ `AGENTMEMORY_URL` (compose) | `profiles/agent-d/SOUL.md` |
| agent-l | Hermes | ✅ `AGENTMEMORY_URL` (compose) | `profiles/agent-l/SOUL.md` |
| agent-j | Hermes | ✅ `AGENTMEMORY_URL` (compose) | `profiles/agent-j/SOUL.md` |
| agent-k | Hermes | ✅ `AGENTMEMORY_URL` (compose) | `profiles/agent-k/SOUL.md` |
| agent-h | Claude Code | ✅ `AGENTMEMORY_URL` (launch env) | `.mailbus/claude/agent-h/` |
| agent-f | Claude Code | ✅ `AGENTMEMORY_URL` (launch env) | `.mailbus/claude/agent-f/` |
| agent-g | Codex | ✅ MCP 直连 | Codex identity preset |
| agent-e | Codex | ✅ MCP 直连 | Codex identity preset |
| agent-m | OpenClaw | ✅ `AGENTMEMORY_URL` (compose) | `/workspace/SOUL.md` |
| n8n | — | ✅ `AGENTMEMORY_URL` (compose) | — |

- **Hermes**: 每个 agent 有独立 profile（`~/.hermes/profiles/<name>/SOUL.md`），dashboard 通过 `--open-profile` 预设对应身份
- **Claude Code**: 启动命令注入 `AGENTMEMORY_URL=http://127.0.0.1:3111`，WSL 宿主机通过 Docker 端口映射访问
- **Codex**: 通过 MCP 协议直连 `iii-engine:3111`，无需中间桥接
- **n8n**: 加入 `mailbus-net` 网络后通过 Docker 内部域名 `iii-engine` 访问
| DeepSeek Gateway | — | `:3000` | Codex 模型路由 |

### 基础设施版本

| 组件 | 版本 |
|------|------|
| Python | 3.12.13 |
| Docker Compose | v2 |
| WSL | Windows NAT 模式 |

### Launch 机制

| 模式 | 实现 | 代码路径 |
|------|------|---------|
| 浏览器 (hermes/opencode) | `launch-agent.sh` → `launch_agent.py` | `tools/ops/launch_agent.py` |
| 浏览器 (codex) | API 直返 URL | `lib/api/handlers_system.py::_get_launch_url` |
| 终端 CLI (Docker 类) | 入队 WSL watchdog → `docker exec -it` | `lib/api/handlers_system.py:1165-1221` |
| 终端 CLI (Claude Code) | `claude_launch.py` → 原生 CLI | `lib/adapters/frameworks/claude_launch.py` |
| 终端 CLI (OpenCode) | 入队 WSL watchdog → `docker exec` | `lib/api/handlers_system.py` |

## Composition binds

| Factory (`lib/composition.py`) | Port / bundle |
|--------------------------------|---------------|
| `build_config_repo` | `CompositeConfigRepo` |
| `build_a2a_transport` | `A2ATransportPort` |
| `build_transport_bundle` | messages + bridged + A2A |
| `build_orchestration_bundle` | FSM / budget / notifier / audit (`MAILBUS_FILE_AUDIT`) |

## Config repositories

- `FileConfigRepository` — `store/config.json` under file_lock RMW
- `MdAgentsConfig` — Vault / `MAILBUS_IDENTITIES_ROOT` agents `*.md` YAML frontmatter
- `CompositeConfigRepo` — agents section: MD wins, else JSON; wired via `build_config_repo`

## Harness rules path

SoT priority (see `lib/adapters/config/sync_layers.py`):

1. explicit `rules_sot` argument  
2. `config.harness.rules_path` (seeded from `config/mailbus/harness.template.json`)  
3. `mail_root/rules`  
4. `MAILBUS_RULES_ROOT`

Chain step templates: `config/mailbus/chains.template.json` (minimal default-dev chain).

## Import linter

`tests/test_import_layers.py` — must stay green.

## Docs

- [AGENTS.md](AGENTS.md) — agent entry
- Package `Overview.md` under `lib/*/Overview.md` and nested packages
- [docs/agent-adapter-layer.md](docs/agent-adapter-layer.md)
- [docs/harness-runtime-spec.md](docs/harness-runtime-spec.md)
- [docs/migration-guide.md](docs/migration-guide.md) — package rename / move reference
- [docs/legacy-bash-eval.md](docs/legacy-bash-eval.md) — bash keep vs Python candidates

## Schema IDs (wire format)

On-disk / example JSON may still use stable tags such as `mailbus-*-v1` or `code-review-report-v1`.  
These are **the single current schema name** for that document type (not dual v1/v2 code paths).  
Python helpers use current names (`is_role_pipeline_task`, `ENGINE_VERSION = "mailbus-smart-routing"`).

## Wave status

Cursor plan waves **0–8** acceptance **100%** (2026-08-10 closeout).  
完整架构文档 SoT：Obsidian `Agent/01-mailbus/016-docs/0161-architecture/`。  
Vault 计划：`Agent/01-mailbus/017-plans/`。  
Older layered-refactor plans are archived for reference only.
