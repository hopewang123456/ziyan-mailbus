# mailbus

File-based **Agent-to-Agent** message bus. Framework-agnostic: Hermes, OpenClaw, Codex, OpenCode, Claude Code, and more via adapters.

No Redis / RabbitMQ required — messages are JSON files, CLI push, agent ack.

## Requirements

**Required**（跑通最小闭环）：
- Python ≥ 3.10
- 一个 agent CLI 或一个远程 A2A endpoint。若两者都没有，`mailbus init` 会 seed 2 个纯文件示例角色（`type: none`），file_bus 即可闭环投递，随后删掉换成你自己的员工即可。

**Optional**：
- Ollama（本机自动中转/路由）
- Docker + Docker Compose（挂载 Agent 小节点 / n8n / ComfyUI）
- AgentMemory、Obsidian Vault —— 增强层，未配置不影响 Core（诊所标灰/黄，不标红）

## Quick start

```bash
git clone https://github.com/hopewang123456/ziyan-mailbus.git
cd mailbus
pip install -e .

# Init store (seeds config.json; 2 example file-based roles when no transport roster present)
mailbus init --data-dir ./store

# Or merge after editing templates
mailbus init --merge --data-dir ./store

# Serve API + built-in scheduler (default port 9814)
mailbus serve --host 0.0.0.0 --port 9814 --data-dir ./store

# Send a message between the seeded example roles
mailbus send agent-executor --msg "Hello" --from agent-dispatcher --data-dir ./store
mailbus status --data-dir ./store
```

Copy [`migrate/env.template`](migrate/env.template) → `.env` and set keys / paths. **Never commit `.env`.**

## Usage

### CLI essentials

| Command | Purpose |
|---------|---------|
| `mailbus init --data-dir ./store` | (Re)build `store/config.json` from seeds + local overrides |
| `mailbus serve --host 0.0.0.0 --port 9814` | HTTP API + built-in scheduler + Cockpit |
| `mailbus send <agent-id> --msg "..." --from <agent-id>` | Push a message into an agent's inbox |
| `mailbus broadcast --msg "..."` | Post a bulletin-board notice |
| `mailbus ack <msg-id> --agent <agent-id>` | Acknowledge receipt (drives retry/backoff) |
| `mailbus scan --data-dir ./store` | Scan inboxes and dispatch pending messages |
| `mailbus status --data-dir ./store` | Show agents / queues / unread |
| `mailbus search --data-dir ./store --query ...` | Search messages and directory |
| `mailbus agent-add <agent-id> --type <framework> --data-dir ./store` | Register an agent |
| `mailbus launch <agent-id> --kind browser` | Start/stop an agent's long-running process |
| `mailbus review / recover / iteration` | Code review, task recover, three-round iteration |
| `mailbus backup --data-dir ./store` | Snapshot the store |

Run `mailbus <cmd> --help` for per-command options.

### Cockpit (Web UI)

After `mailbus serve`, open `http://127.0.0.1:9814/`:

- **Fleet / inbox** — live agent status, unread messages, send & ack
- **Tasks** — pipeline / FSM state, assign, audit (`?reviewer=`), recover
- **Settings** — form-based **agent config** and **model config** (agent-type / internal LLM / external services); every field is edited as a form and saved back to JSON; legacy JSON editors remain for `frameworks / mailbus_codex / mailbus_claude`
- **Settings / Asset paths** — skills / rules / identities roots as "default / custom": default uses in-repo junction dirs (`skills/` `rules/` `identities/`, SoT in the Obsidian Vault); custom writes `.env` (`MAILBUS_SKILLS_ROOT` / `MAILBUS_RULES_ROOT` / `MAILBUS_IDENTITIES_ROOT`), restart required
- **Clinic / doctor** — one-click health checks (Hermes readiness, compose drift, token budget, …)

### Sending an A2A message

```bash
# agent-b asks agent-a for a design pass
mailbus send agent-a --msg "请评审 order-intake 流程" --from agent-b --data-dir ./store

# wait for the inbox to be picked up by the scheduler, then inspect
mailbus status --data-dir ./store
mailbus search --data-dir ./store --query order-intake
```

### LLM（自动中转的必要条件）

自动业务中转（工作流未指定下一棒时，由 Planner 选下一个 agent）需要**至少一家可用 LLM**：

| 选项 | 配置方式 | 说明 |
|------|----------|------|
| 本地 Ollama | 默认 `http://127.0.0.1:11434`，模型 `qwen2.5:3b-instruct-q4_K_M` | `providers.local` |
| 远程 OpenAI-compatible | 设 `MAILBUS_INTERNAL_LLM_API_KEY`（或改 `providers.remote.api_key_env`） | `providers.remote`（默认 DeepSeek 兼容端点） |
| 测试 stub | 无需配置 | 无网络 CI 用，返回确定性计划 |

- 配置集中在 `store/config.json` 的 `mailbus_internal_llm` 段：`enabled` / `providers` / `provider_priority`（默认 `["local", "remote"]`，本地优先）。Dashboard「模型配置」页可编辑；seed 见 [`config/llm/internal-llm.json`](config/llm/internal-llm.json)。
- **Ollama 是可选**：无 Ollama 时用远程 LLM 做路由建议中转。
- **只做人工指定下一棒或写死工作流时可不配 LLM**：把 `mailbus_internal_llm.enabled` 置 `false` 即可，此时自动中转不可用。
- 诊所会探测 provider 链是否至少一家可达（`/api/llm/probe`），不可达标黄不标红。

### Docker (public minimal stack)

Does **not** replace a full local team compose. For GitHub / new users:

```bash
cd docker-agents
docker compose -f compose.public.yml up -d --build
```

Optional: `compose.public.override.example.yml` → `compose.public.override.yml`.

Local full-stack users keep using `docker-compose.yml` + gitignored `docker-compose.override.yml`.

### Team stack (Linux / macOS / Windows)

Canonical CLI (no PowerShell required on Linux/macOS):

```bash
python tools/mailbus.py doctor
python tools/mailbus.py start          # native; skip Windows/WSL Ollama glue on Linux
python tools/mailbus.py docker restart-mailbus
python tools/mailbus.py docker start-n8n
python tools/mailbus.py docker up-comfyui
python tools/mailbus.py docker ensure-ollama
```

#### Thin launch scripts

Two thin wrappers are provided (Windows / Linux) — they only locate the repo and call `python tools/mailbus.py start`:

| Platform | Script | Prerequisites |
|----------|--------|---------------|
| Windows | `scripts/start-mailbus.bat` | Python 3.11+ in `PATH` (`python` or `py -3`); Docker Desktop + WSL for the team stack |
| Linux / macOS | `scripts/start-mailbus.sh` | `python3` ≥ 3.11 in `PATH`; Docker for the team stack |

```bash
# Linux / macOS
bash scripts/start-mailbus.sh
```

```bat
:: Windows (double-click or from a terminal)
scripts\start-mailbus.bat
```

All other operations use `python tools/mailbus.py <cmd>` (start / stop / doctor / smoke / portproxy / docker …).

#### Deployment differences

| | **Linux / macOS (native)** | **Windows + WSL team stack** |
|--|----------------------------|------------------------------|
| Day-to-day start | `python tools/mailbus.py start` or `mailbus serve` | Same Python entry; optional thin `scripts/start-mailbus.bat` |
| Browser → API | Open `http://127.0.0.1:9814/` directly | If serve runs **inside WSL** and the browser is on Windows, localhost may break when WSL IP / `wslrelay` goes stale |
| Port forwarding | **Not needed** (`portproxy` is a no-op) | Run `python tools/mailbus.py portproxy` or `windows/fix-wsl-localhost.ps1` (UAC). See [`windows/README.md`](windows/README.md) |
| Ollama glue | Host Ollama / `MAILBUS_OLLAMA_URL` | Windows host Ollama + optional WSL proxy (start path on `win32`/`wsl` only) |

Windows launch wrappers only call Python. All Windows-specific **portproxy** scripts live under [`windows/`](windows/).

#### External plugins (frameworks & integrations)

Load-time discovery (no hot-reload):

| Kind | Config | Env | pkg entry-points |
|------|--------|-----|------------------|
| Framework adapters | `frameworks.plugins` | `MAILBUS_FRAMEWORK_PLUGINS` | `mailbus.frameworks` |
| Integrations | `integrations.plugins` | `MAILBUS_INTEGRATION_PLUGINS` | `mailbus.integrations` |

Specs are `module` or `module:callable` (callable should call `register_framework` / `register_integration`). Strict fail: `*_PLUGINS_STRICT=1`.

## Secrets & private config

**Do not commit secrets or personal agent rosters.** Prefer local files + published examples (no encryption-in-git).

| Keep local (gitignored) | Publish instead |
|-------------------------|-----------------|
| `.env`, `store/secrets.json`, `store/` | [`migrate/env.template`](migrate/env.template), [`docker-agents/.env.example`](docker-agents/.env.example) |
| `access/transport/<your-agent>/` | [`examples/transport/`](examples/transport/) (`agent-a` / `agent-coder` / `agent-chat`) |
| `config/agents/<id>.override.json` | [`config/agents/*.override.example.json`](config/agents/) |
| `config/mailbus/launch-ports.json` | [`config/mailbus/launch-ports.example.json`](config/mailbus/launch-ports.example.json) |
| `access/external-tools/registry.json`, `grants.json` | `access/external-tools/*.example.json` |
| `docker-compose.override.yml`, ComfyUI host mounts | `*.override.example.yml` |

**Runtime always reads files without `.example` in the name.** After clone: copy `foo.example.json` → `foo.json`, fill in your values / agent ids. See [`config/README.md`](config/README.md).

Non-sensitive shared seeds under `config/` (pipeline, agent-types, …) stay committed as plain JSON.

## 配置指南

### 配置入口一览

| 文件 | 作用 | 提交策略 |
|------|------|----------|
| `store/config.json` | 主配置：项目信息、`agents` 注册、`agent_types`、`smart_routing` 等 | gitignored（`mailbus init` 从 seed 生成） |
| `config/agents/<id>.override.json` | 单 agent 覆盖：模型、launch 模板、超时 | 本机文件（提交 `<id>.override.example.json`） |
| `config/mailbus/launch-ports.json` | agent id → 浏览器/API 端口映射 | 本机文件（提交 example） |
| `access/transport/<id>/transport.json` | agent 的 transport 注册（框架、路径、可达性） | 本机文件（提交到 `examples/transport/`） |
| `config/mailbus/agent-types.json` | 框架 push 命令模板 + 模型 CLI 参数 + launch 模板 | 可直接提交 |
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
| `name` / `role` | string | 显示名 / 职责（Cockpit 展示用） |
| `models` | string[] | 模型名列表，需在 `agent_types.models` 中定义对应的 CLI 参数 |
| `enabled` | bool | 是否启用该 agent（`mailbus init` 后默认状态） |
| `max_concurrency` | int | 并发上限（默认 1） |
| `inbox` | string | 收件箱 JSON 路径 |
| `profile_paths` | object | `identity` / `soul`（人设文件）、`skills_dirs`、`memory_dir`（技能/记忆根目录） |
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

`launch.template` 引用 `config/mailbus/agent-types.json` 里的 `launch_templates`（如 `claude_host`、`codex_docker`、`hermes_dashboard`、`openclaw_gateway`、`opencode_cli`），模板定义了 cli / browser / desktop 三种启动形态。

### 注册一个新 agent（完整流程）

1. 建 `access/transport/<your-id>/transport.json`（可复制 `examples/transport/agent-coder/transport.json` 改路径）。
2. 建 `config/agents/<your-id>.override.json`（复制 `coder.override.example.json`）。
3. 在 `config/mailbus/launch-ports.json` 给 `<your-id>` 映射端口（复制 `launch-ports.example.json`）。
4. 在 `store/config.json` 的 `agents` 里登记 `<your-id>`（参考 `examples/config.example.json`）。
5. 重跑 `mailbus init --merge --data-dir ./store`（或启动时自动发现），再到 Cockpit **设置**页确认/启用。

### 模型与 push 命令

`config/mailbus/agent-types.json` 的 `models` 定义每个模型对每个框架的 CLI 参数（例如 `deepseek-flash` → `opencode: --model deepseek/deepseek-chat`）。新增模型要保证在 `store/config.json` 的 `agents` 与 override 里引用一致；框架 `push` 命令模板（`hermes chat …`、`claude -p 'MSG'` 等）在同一文件顶层，`type: "none"` 表示纯文件通信、无 CLI 推送。

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

**运行环境字段的 SoT 在实例卡**（不在角色卡）：`run_target` / `install_path` / `host` / `custom_paths` / `distro` 由实例卡唯一持有，角色卡只读继承（`instance_id` 指针），不再双写。同一框架可多端多实例（如 `hermes@docker` 与 `hermes@wsl@ubuntu` 各建一个实例、各自加载角色）。

**enabled 双层级**：角色级 `enabled` = 员工「退役 / 工作」；实例级 `enabled` = 容器是否继续监测（关闭则下架全部角色）。扫描验证（`/api/agents/scan`）写回实例级 `install_path/run_target/distro/gate_passed`，不覆盖角色级 `enabled`。mailbus 不改变 agent 框架自身配置，只做配置读取与通信桥接。

## 跨环境接入与浏览器白名单

mailbus 无论跑在 **Windows / WSL / Linux native / Docker**，都能统一探测 agent 容器、浏览器端口与第三方组件，并生成可用的浏览器 URL。默认仅本机可访问（`127.0.0.1`，Docker 内 `host.docker.internal`）；通过白名单可放行局域网/广域网。

核心原语收敛在 `lib/infra/runtime_net.py`（`runtime_env` / `browser_host` / `browser_base_url` / `resolve_loopback` / `allowed_browser_hosts`）。

### 浏览器白名单（`browser_hosts`）配置位置

| 来源 | 配置位置 | 示例 |
|------|----------|------|
| 主配置（优先级低于 env） | `store/config.json` 顶层 `browser_hosts` 数组（Cockpit 设置页可编辑，或直接编辑文件） | `"browser_hosts": ["192.168.1.0/24", "10.0.0.5"]` |
| 环境变量（覆盖之） | `MAILBUS_BROWSER_HOSTS`（逗号分隔 IP/CIDR） | `MAILBUS_BROWSER_HOSTS=192.168.1.0/24,10.0.0.5` |

- 两者皆空 = **默认仅本机 `127.0.0.1`**（现状行为，零变化）。
- 白名单里第一个**具体 IP**（非 CIDR）会被用作生成的 URL host（例如 `"192.168.1.50"` → 生成 `http://192.168.1.50:9120/…`）；纯 CIDR 网段只用于放行判断，URL 仍回退本机 host。
- **配置了白名单 ≠ 端口已对外放行**。真正放行由 compose 端口发布（默认 localhost）、`serve --host`（默认 `127.0.0.1`）、各 agent 浏览器鉴权、以及自建反代/防火墙共同承担。

### agent 浏览器鉴权（`agents.<id>.auth`）

每个 agent 下可选 `auth` 块（Cockpit 设置页「浏览器鉴权」可配）：

```json
"agents": {
  "agent-m": { "type": "openclaw", "auth": { "mode": "token", "token_ref": "openclaw_gateway" } },
  "agent-a": { "type": "hermes_profile", "auth": { "mode": "basic", "username_ref": "hermes_a", "password_ref": "hermes_a" } }
}
```

- `mode: none`（默认）= 无凭据，仅本机访问。
- `mode: token`（OpenClaw）= 跳转 URL 注入 `?token=`。
- `mode: basic`（Hermes / ttyd）= 跳转 URL 注入 userinfo（`http://user:pass@host:port/`）。
- `mode: header`（预留）= 走 mailbus 反代注入 Authorization header。
- 敏感字段用 `*_ref` 引用 `store/secrets.json` 的 `browser_auth.<agent>`，避免明文进 `config.json`。

### 各 agent 浏览器入口鉴权清单 + 免密路径

**边界**：mailbus 只管「浏览器入口」鉴权与免密跳转；agent 的 **LLM provider 鉴权归 agent 内部**（Claude Code 用 cc-switch、Codex 用 DeepSeek 中转 key，配在容器/宿主内，mailbus 不读取不注入）。

| 入口 | 端口 | 鉴权机制 | 免密 = mailbus 已配置/已生成该 agent 浏览器凭据 |
|------|------|----------|----------------------------------------------|
| Hermes dashboard | 9120–9127 | 固定 session token（`HERMES_DASHBOARD_SESSION_TOKEN`） | mailbus 生成固定 token 存 `store/secrets.json` 并注入容器 env（跨重启不变）；浏览器首次输入后记住 |
| Codex Web UI | 9220/9240 | password + HttpOnly cookie `codex_web_local_token`（1 年 + 重启保持） | mailbus 生成/读取密码注入 `CODEX_UI_PASSWORD`；`CODEX_HOME` 卷持久化，首次输密码后 cookie 记住 |
| Codex ttyd | 9250 | ttyd Basic Auth（`-c`） | mailbus 自生成 user/pass（`browser_auth.<agent>`）→ 启动脚本 `-c` + URL userinfo |
| Claude Code ttyd | 9260 | ttyd Basic Auth（`-c`） | 同上（`browser_auth.<agent>`） |
| OpenClaw gateway | 18789/18790 | `--auth token` | mailbus 读 `OPENCLAW_GATEWAY_TOKEN` env / `openclaw.json` gateway.auth / auth 块 → URL `?token=` |
| OpenCode | 无浏览器 | 纯 CLI（`browser.kind=none`） | 不参与白名单/URL 生成；LLM provider key 走容器内配置 |

### 免密原理（接入原则）

1. **「免密」= mailbus 已在 Agent 卡片 / `secrets.json` 收口该 agent 浏览器凭据**（鉴权仍属 agent 本体）。实现上可为 URL 注入、容器 env、或首次输入后浏览器记住——按框架而异；**过期后需重新登录**。
2. **LLM provider 鉴权不归 mailbus 管**（cc-switch / DeepSeek 中转 key 是 agent 内部配置）。
3. **白名单放行 = 逐 agent 浏览器鉴权门槛**：有浏览器凭据的 agent 才允许非本机 URL；无凭据 agent 非本机下退回 `127.0.0.1`；无浏览器 agent（OpenCode）不参与。
4. **广域网放行额外强制**：有效 token（非 `change-me`）+ 提示 HTTPS 反代（Basic Auth userinfo 会进 URL 历史，公网必须反代）。
5. **运行端**：实例级 `run_target` = `windows|wsl|linux|docker`，经 `lib/adapters/runtime` 分发器选型；`distro`（`auto|ubuntu|centos`）区分 Linux 发行版；Windows↔WSL 可作跨边界测试（详见架构文档）。

### 局域网/广域网安全清单

- 默认空白名单 = 仅 `127.0.0.1`，行为与现状完全一致。
- 放行局域网：在 `browser_hosts` 配 CIDR（如 `192.168.1.0/24`）或具体 IP；确保该 agent 已有浏览器凭据（否则仍退回本机）。
- 放行广域网：必须有效 token + HTTPS 反代；`serve --host 0.0.0.0` + 防火墙放行目标端口 + 各 agent 浏览器鉴权缺一不可。
- 自动生成的凭据存 `store/secrets.json`（gitignored）；不要提交。

## 智能体员工花名册

**默认名册**：`mailbus init` 在无 `access/transport/` 与 team-pack 名册时，seed 2 个纯文件示例角色（`agent-dispatcher` 调度员、`agent-executor` 执行者，见 [`config/mailbus/example-agents.json`](config/mailbus/example-agents.json)）。**运行时名册 SoT 永远是 `store/config.json` 的 `agents` 段**（含 `agent_instances` 实例卡），transport / Vault 数据只做增强合并。删掉示例角色、换成你自己的员工即可，不允许任何硬编码人数/路径。

添加员工：Cockpit **设置页** 新增实例卡 → 加载角色；或按「注册一个新 agent」流程落 transport 文件后 `mailbus init --merge`。

参见 [`ARCHITECTURE.md` § Agent roster](ARCHITECTURE.md#agent-roster智能体员工花名册) 获取完整版本和访问端口。

> 下表为**完整示例名册**（demo ids，非默认 seed）。实际名册以 `store/config.json` 为准。

| 代号 | 名称 | 框架 | 浏览器端口 | 认证 |
|------|------|------|-----------|------|
| `agent-a` | Agent A | Hermes | `:9120` | admin / change-me |
| `agent-c` | Agent C | Hermes | `:9121` | admin / change-me |
| `agent-d` | Agent D | Hermes | `:9122` | admin / change-me |
| `agent-l` | Agent L | Hermes | `:9125` | admin / change-me |
| `agent-j` | Agent J | Hermes | `:9126` | admin / change-me |
| `agent-k` | Agent K | Hermes | `:9127` | admin / change-me |
| `agent-g` | Agent G | Codex | `:9240` | Web UI |
| `agent-e` | Agent E | Codex | `:9241` | Web UI |
| `agent-h` | Agent H | Claude Code | — | 终端 (WSL) |
| `agent-f` | Agent F | Claude Code | — | 终端 (WSL) |
| `agent-i` | Agent I | OpenCode | — | 终端 |
| `agent-m` | Agent M | OpenClaw | `:18789` | token=change-me |
| `agent-n` | Agent N | OpenClaw | `:18790` | token=change-me |

> 上表为**示例名册**（demo ids）。实际名册以 `store/config.json` 的 `agents` 段为准；凭据通过 `.env` / `store/secrets.json` 配置，**不要提交真实凭据**。

### 集成（可发现 · 可探针 · 可跳过）

集成是**可选增强**：未配置 = 诊所跳过/灰标，不拖 Core 变红。Dashboard「集成」页可查看、探针。

| 集成 | 必配? | 配置方式 | 说明 |
|------|-------|----------|------|
| n8n | 可选 | `docker compose -f docker-compose.n8n.yml up -d`；`N8N_BASE_URL` / `N8N_PUBLISH_WEBHOOK_URL` | 工作流编排；本版不做 workflow CRUD/编排 UI |
| ComfyUI | 可选 | `docker up-comfyui`；`COMFYUI_BASE_URL` / `COMFYUI_CHECKPOINT` | 生图；本版不做编排 UI |
| AgentMemory | 可选 | `AGENTMEMORY_URL`（默认 `:3111`）；`MEMORY_BRIDGE_AGENTMEMORY` | 记忆桥接；未配置 SQLite-only 降级 |
| Ollama | 可选 | `services.ollama`（默认 `:11434`） | 本机路由/自动中转 |
| external-tools | 可选 | `access/external-tools/registry.json`（推荐唯一 SoT） | 外部工具注册 |
| plugins | 可选 | `integrations.plugins` / `MAILBUS_INTEGRATION_PLUGINS` | 自定义集成，`mailbus.integrations` entry-point |
| Cockpit | 必配 | `:9814` | 主控制台（随 `mailbus serve` 起） |

注册你自己的智能体在 cockpit **设置** 页（自动发现后默认关闭）。

## 诊所（Clinic / doctor）

`mailbus serve` 后 Cockpit 的 **Clinic / doctor** 页提供一键健康检查，按**分层**展示：

| 层 | 含义 | 失败后果 |
|----|------|----------|
| **Core** | 配置合法、示例名册存在、信封/transport 合法、LLM 门禁语义、API 存活 | 标红，需修复才能跑通闭环 |
| **Host** | 依赖宿主机/容器的工具（compose drift、WSL/Ollama glue、浏览器入口探活等） | 容器内**不标红**，提示到宿主机执行 |
| **Integrations** | n8n / ComfyUI / AgentMemory / Ollama 等可选集成 | 未配置 = 跳过/灰标；不可达标黄不标红 |

**Core 绿即可跑通最小闭环**（示例角色 + 统一信封 + file_bus 投递）。Host/Integrations 项按需在宿主机或配置后重跑。

## 本版不做（防预期膨胀）

- A2A **streaming**（stub 保留，债务）
- **工单**字段 / 状态机 / 流转细则（下一 session）
- n8n / ComfyUI **编排 UI**（workflow CRUD）
- Hermes identities **自动同步**验收
- sqlite_fts / 向量 RAG 升级
- 强制每人独立 transport 才能启动

这些能力不会被当成「已交付」，避免误判完成度。

## 自愈与看门狗（防假死）

`mailbus serve` 是**多线程** HTTP 服务，但若进程整体僵死（accept 循环卡住 / 线程死锁），端口仍 `LISTENING` 却对所有请求返回 `Empty reply from server`。为此内置三层自愈（均**纯 Python、跨平台**）：

| 层 | 机制 | 说明 |
|----|------|------|
| **L0 现场** | `faulthandler` | 服务启动即启用；看门狗触发或致命信号时 dump 全部线程栈到 `store/logs/{faulthandler,watchdog-stall}.log`，用于定位假死根因 |
| **L1 进程内** | 看门狗线程 | 每 10s 探 `GET /api/health`，连续 3 次失败 → dump 现场 → 自尽（退出码 70），「宁死也不假死」 |
| **L2 进程外** | `tools/mailbus_watchdog.py` | 独立守护进程包住 serve，探 `/api/health` 失败或 serve 异常退出 → kill + 重启；可抵抗 L1 也救不了的彻底僵死 |

**推荐用法**（Windows / Linux / macOS 通用）：

```bash
# 直接起（内置 L0+L1）
python -m bus serve --host 0.0.0.0 --port 9814 --data-dir ./store

# 或加 L2 外部守护（生产推荐）
python tools/mailbus_watchdog.py --data-dir ./store --host 0.0.0.0 --port 9814
```

- 存活探针：`GET /api/health` → `{"status":"ok","pid":...,"ts":...}`（无 IO、无依赖）。
- 配置（环境变量）：`MAILBUS_SELF_WATCHDOG=0` 关闭 L1；`MAILBUS_WATCHDOG_INTERVAL`（默认 10s）、`MAILBUS_WATCHDOG_THRESHOLD`（默认 3 次）、`MAILBUS_WATCHDOG_MAX_BACKOFF`（L2 重启退避上限，默认 60s）。

## Cockpit

Open `http://127.0.0.1:9814/` after `mailbus serve`.  
Legacy UI: `/legacy` if present.

配置（设置）页中**智能体配置**与**模型配置**（智能路由 / Internal LLM / 外部服务）已表单化编辑——每个字段直接表单输入，保存后仍以 JSON 落盘；`frameworks / mailbus_codex / mailbus_claude` 保留 JSON 折叠编辑器。详见 [`config/README.md`](config/README.md)。

## Architecture

Ports & Adapters layout (see [`ARCHITECTURE.md`](ARCHITECTURE.md) and [`AGENTS.md`](AGENTS.md)):

```
tools/ · lib/api/ → lib/application/ → lib/interfaces/ ← lib/adapters/
                         ↓
               lib/domain/ · lib/core/
                         ↓
                    lib/infra/
```

| Layer | Role |
|-------|------|
| `lib/interfaces/` | Protocol interfaces (ex-`ports`) |
| `lib/core/a2a/` | A2A core (ex-`lib/transport`) |
| `lib/application/` | Use cases (workflow, harness, scan, push, orchestration, …) |
| `lib/adapters/` | frameworks, plane, config (`CompositeConfigRepo`), transport, container (`resolver.py`), … |
| `lib/infra/` | clock, paths, `mbus_log`, internal LLM bootstrap |

Composition root: `lib/composition.py` only (`build_a2a_transport`, `build_transport_bundle`, `build_config_repo`, …).  
Each package ships an `Overview.md` map. Path migration: [`docs/migration-guide.md`](docs/migration-guide.md).  
Harness rules: `config.harness.rules_path`; chain templates: `config/mailbus/chains.template.json`.

## Docs

- Architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- Agent entry: [`AGENTS.md`](AGENTS.md)
- Migration (ports → interfaces, transport → core/a2a): [`docs/migration-guide.md`](docs/migration-guide.md)
- Legacy bash eval: [`docs/legacy-bash-eval.md`](docs/legacy-bash-eval.md)
- Adapter layer: [`docs/agent-adapter-layer.md`](docs/agent-adapter-layer.md)
- Harness: [`docs/harness-runtime-spec.md`](docs/harness-runtime-spec.md)
- Env template: `migrate/env.template`

## License

MIT
