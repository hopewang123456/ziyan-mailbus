# Mailbus Architecture（Ports & Adapters）

> Layer: docs · Owner: 子言 · local_root: `E:\ai_tools\mail`  
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
| `lingzhao` | 灵昭 | Hermes · dashboard | hermes-agent 0.17.0 | `:9120` (免登) | `docker exec hermes chat` | `profiles/lingzhao/SOUL.md` |
| `lingjin` | 灵锦 | Hermes · dashboard | hermes-agent 0.17.0 | `:9121` (免登) | `docker exec hermes chat` | `profiles/lingjin/SOUL.md` |
| `lingxi` | 灵曦 | Hermes · dashboard | hermes-agent 0.17.0 | `:9122` (免登) | `docker exec hermes chat` | `profiles/lingxi/SOUL.md` |
| `lingxun` | 灵巡 | Hermes · dashboard | hermes-agent 0.17.0 | `:9125` (免登) | `docker exec hermes chat` | `profiles/lingxun/SOUL.md` |
| `lingtuo` | 灵拓 | Hermes · dashboard | hermes-agent 0.17.0 | `:9126` (免登) | `docker exec hermes chat` | `profiles/lingtuo/SOUL.md` |
| `lingzhang` | 灵彰 | Hermes · dashboard | hermes-agent 0.17.0 | `:9127` (免登) | `docker exec hermes chat` | `profiles/lingzhang/SOUL.md` |
| `lingyun` | 灵云 | Claude Code (host) | 2.1.226 | — | `claude --project` (WSL) | `.mailbus/claude/lingyun/` |
| `lingyan` | 灵验 | Claude Code (host) | 2.1.226 | — | `claude --project` (WSL) | `.mailbus/claude/lingyan/` |
| `lingxiao` | 灵霄 | Codex · Docker | codex-cli 0.147.0 | `:9240` (Web UI) | `docker exec codex` | Codex identity preset |
| `lingjian` | 灵鉴 | Codex · Docker | codex-cli 0.147.0 | `:9241` (Web UI) | `docker exec codex` | Codex identity preset |
| `dali` | 大力 | OpenCode · Docker | opencode 1.18.16 | — | `docker exec opencode cli` | — |
| `xiaoqi` | 小七 | OpenClaw · Docker | 2026.7.1-2 | `:18789/chat?token=ziyan-team` | `docker exec openclaw tui` | `/workspace/SOUL.md` |
| `yige` | 一哥 | OpenClaw · Docker | 2026.7.1-2 | `:18790/chat?token=ziyan-team` | `docker exec openclaw tui` | `/workspace/IDENTITY.md` |

### 集成工具

| 工具 | 版本 | 端口 | 说明 |
|------|------|------|------|
| n8n | 1.76.1 | `:5678` | 独立 compose 栈，可视化 workflow 编排 |
| AgentMemory | iii-engine | `:3111` | 共享记忆存储 |

### Agent Memory 连接状态

| Agent | 框架 | AgentMemory 连接 | 身份文件 |
|-------|------|-----------------|---------|
| lingzhao | Hermes | ✅ `AGENTMEMORY_URL` (compose) | `profiles/lingzhao/SOUL.md` |
| lingjin | Hermes | ✅ `AGENTMEMORY_URL` (compose) | `profiles/lingjin/SOUL.md` |
| lingxi | Hermes | ✅ `AGENTMEMORY_URL` (compose) | `profiles/lingxi/SOUL.md` |
| lingxun | Hermes | ✅ `AGENTMEMORY_URL` (compose) | `profiles/lingxun/SOUL.md` |
| lingtuo | Hermes | ✅ `AGENTMEMORY_URL` (compose) | `profiles/lingtuo/SOUL.md` |
| lingzhang | Hermes | ✅ `AGENTMEMORY_URL` (compose) | `profiles/lingzhang/SOUL.md` |
| lingyun | Claude Code | ✅ `AGENTMEMORY_URL` (launch env) | `.mailbus/claude/lingyun/` |
| lingyan | Claude Code | ✅ `AGENTMEMORY_URL` (launch env) | `.mailbus/claude/lingyan/` |
| lingxiao | Codex | ✅ MCP 直连 | Codex identity preset |
| lingjian | Codex | ✅ MCP 直连 | Codex identity preset |
| xiaoqi | OpenClaw | ✅ `AGENTMEMORY_URL` (compose) | `/workspace/SOUL.md` |
| n8n | — | ✅ `AGENTMEMORY_URL` (compose) | — |

- **Hermes**: 每个 agent 有独立 profile（`~/.hermes/profiles/<name>/SOUL.md`），dashboard 通过 `--open-profile` 预设对应身份
- **Claude Code**: 启动命令注入 `AGENTMEMORY_URL=http://127.0.0.1:3111`，WSL 宿主机通过 Docker 端口映射访问
- **Codex**: 通过 MCP 协议直连 `iii-engine:3111`，无需中间桥接
- **n8n**: 加入 `ziyan-net` 网络后通过 Docker 内部域名 `iii-engine` 访问
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
Vault Obsidian SoT: `Projects/mailbus/plans/2026-08-10-arch-deep-cleanup.md`.  
Older layered-refactor plans are archived for reference only.
