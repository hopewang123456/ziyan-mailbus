# ziyan-mailbus

**Break down the barriers between AI Agents. True A2A (Agent-to-Agent) communication, framework-agnostic.**

ziyan-mailbus is an independent, decoupled, lightweight **file-based message bus** designed for multi-agent teams. No framework lock-in, no agent code modification — the CLI is the only contract. Plug and play.

> No Redis / RabbitMQ / Database required. Messages stored as JSON files. CLI push delivery with bidirectional ACK confirmation.

## Design Philosophy

- **True A2A** — Let agents built with different frameworks talk to each other freely. Not tied to any specific agent implementation.
- **Files as Communication** — Messages stored as JSON files, zero middleware dependency. Backup = `cp`, migrate = `scp`.
- **Bidirectional Confirmation** — CLI push + Agent writes ACK. No "fire and forget" illusion.
- **Queue-then-Push** — Urgent messages first, normal messages queued, batched per agent.
- **Fault Isolation** — 3 failed push attempts → error log → monitoring agent scans logs for recovery.
- **Agent Type Abstraction** — Unified `agent_types` config. Supports Hermes, OpenClaw, Cline, OpenCode, and more.
- **Plug and Play** — Zero agent code modification. The CLI is the only contract.

## Prerequisites

- **Python ≥ 3.10**
- **CLI tools** for your agents (Hermes, OpenClaw, Cline, OpenCode, etc.)
- **API Keys** — configured via `.env` file (see `examples/config.example.json`)
- **AgentMemory** (optional) — persistent memory for message history
  - Install: `npm install -g @agentmemory/agentmemory`
  - Start: `agentmemory` (default: http://localhost:3111)
  - Bridge: mailbus automatically syncs acknowledged messages to AgentMemory

## Quick Start

```bash
# 1. Install
git clone https://github.com/hopewang123456/ziyan-mailbus.git
cd ziyan-mailbus
pip install -e .

# 2. Initialize
mailbus init --data-dir /path/to/your/store

# 3. Register an Agent
mailbus agent-add agent-a --cli "your-cli --message" --role "your role"

# 4. Start the bus (recommended: built-in Scheduler, no crontab)
mailbus serve --host 0.0.0.0 --port 9814 --data-dir /path/to/your/store
# SchedulerHub runs scan, memory_bridge, pipeline_watchdog automatically

# Or scan manually:
mailbus scan

# 5. Send a message
mailbus send agent-a --msg "Hello, please handle this task" --from lingzhao
mailbus broadcast --msg "System maintenance notice"

# 6. Check status
mailbus status
mailbus status --failed
```

## Cross-Platform Deployment

mailbus is **pure Python + filesystem** — on **Linux and macOS** you can run it natively without WSL or any Windows-specific bridge. The default API port is **9814** (`lib/constants.py`).

### Port reference

| Deployment | API port | Notes |
|------------|----------|-------|
| Native `mailbus serve` | **9814** | Linux / macOS / Windows |
| Docker `mailbus` service | **9812** | Inside `docker-agents/` compose network; host mapping may differ |
| n8n webhook | **5678** | Optional; video publish drill |
| AgentMemory | **3111** | Optional |
| Lingyun Claude ttyd | **9260** | WSL host · Claude Code pro |
| Lingyan Claude ttyd | **9261** | WSL host · Claude Code QA |

### Developer tier dispatch (2026-06-25)

For `role_type=8` (developer): **filter candidates by `model_tier`, then least_load + round-robin**.

| tier | Agents |
|------|--------|
| `pro` (requires `MAILBUS_ALLOW_PRO=1`) | lingyun |
| `flash` / default | dali, lingxiao |

Set `constraints.dispatch.model_tier` on the task envelope. Offline agents are auto-excluded with failover. See [`rules/model-routing.md`](rules/model-routing.md).

### Linux / macOS (recommended)

No WSL bridge required — n8n/ComfyUI on the same machine use `http://127.0.0.1:5678` / `8188` directly.

```bash
# 1. Install
git clone https://github.com/hopewang123456/ziyan-mailbus.git
cd ziyan-mailbus
python3 -m venv .venv && source .venv/bin/activate   # optional
pip install -e .

# 2. Initialize data dir
mailbus init --data-dir ./store
cp examples/config.example.json store/config.json   # then edit agents / keys

# 3. Environment (.env in project root — do not commit)
cat >> .env <<'EOF'
MAILBUS_API_TOKEN=your-secret-token
GITHUB_TOKEN=ghp_...                    # optional: platform-scout github_issues
N8N_PUBLISH_WEBHOOK_URL=http://127.0.0.1:5678/webhook/mailbus-multi-publish
EOF

# 4. Start bus (built-in SchedulerHub: scan, platform-scout, pipeline-repair, …)
mailbus serve --host 127.0.0.1 --port 9814 --data-dir ./store
# Or background:
bash tools/restart-mailbus.sh 9814

# 5. Optional: n8n sidecar
bash docker-agents/start-n8n.sh
bash tools/setup-n8n.sh

# 6. Acceptance
python3 tools/run-final-acceptance.py
python3 tools/validate-order-intake.py --data-dir store
# Dashboard: open docs/index.html (API base defaults to http://127.0.0.1:9814)
```

**systemd (optional):** see `docker-agents/install-systemd.sh` and `docker-agents/docker-agents.service`.

### Windows (native Python + optional WSL Docker)

When **mailbus runs on Windows** and **n8n runs in WSL Docker**, `localhost:5678` may be unreachable from Python — mailbus uses `lib/n8n/wsl_bridge.py` automatically as fallback.

```powershell
pip install -e .
mailbus init --data-dir store
# Configure .env (same vars as Linux)

# Start / restart native serve (default 9814)
.\tools\restart-mailbus.ps1

# n8n in WSL Docker
.\tools\setup-n8n.ps1          # or -Reset to rebuild workflow volume
# Or: wsl bash docker-agents/start-n8n.sh

python tools\run-final-acceptance.py
```

Tips:
- Prefer **WSL mirrored networking** or port forwarding if you want to avoid the WSL bridge.
- Docker Desktop on Windows: full team stack via `wsl bash docker-agents/start-team.sh`.

### Docker full agent team

For Hermes / OpenClaw / Cline containers sharing one `store/` volume:

```bash
cd docker-agents
cp .env.example .env          # fill API keys
bash start-team.sh            # compose up + health checks
bash mailbus-pipeline-e2e.sh  # end-to-end regression
```

Inside the mailbus container the API listens on **9812** (see `docker-compose.yml`). Host scripts under `docker-agents/*.sh` use that port — this is intentional and different from native **9814**.

### Optional components

| Component | Purpose | Setup |
|-----------|---------|-------|
| **n8n** | Multi-channel publish (video drill) | `setup-n8n.sh` / `setup-n8n.ps1` |
| **ComfyUI** | Image generation step | `docker-agents/start-comfyui-gpu.sh` |
| **AgentMemory** | Long-term message memory | `npm i -g @agentmemory/agentmemory && agentmemory` |

### Verification checklist

```bash
python3 tests/run_all.py                          # unit tests
python3 tools/validate-scheduler.py --url http://127.0.0.1:9814
python3 tools/smoke-platform-scout.py --data-dir store
python3 tools/validate-order-intake.py --data-dir store
python3 tools/run-final-acceptance.py
```

### Roadmap gaps (see `plans/`)

Still tracked but not blocking native Linux deploy:

| Item | Status |
|------|--------|
| Phase1 `platform-scout` → lingtuo task notify | Done (`after_scout_notify_agent`) |
| `validate-order-intake.py` | Done |
| Lingxiao auto-ack / chat `-q` timeout | Done (file-task push + phantom + CLI timeout reset) |
| Agent permission persistence | Done (`permission.json` + API normalize) |
| Token stats Dashboard | Done (`/api/stats` token_estimates) |
| Commercial role-flow (lingtuo → lingzhao) | Done (role-flow pursue + intake gates) |
| Lingtuo Hermes profile 9126 | Done (`init-profiles.sh` + config) |

## Core Features

| Feature | Description |
|---------|-------------|
| **Zero Dependencies** | Pure Python + filesystem. No Redis / MQ / DB. |
| **Bidirectional ACK** | CLI push → Agent writes ACK → bus updates status. No message loss. |
| **Message Protocol** | Structured `type` + `action` fields. Agents don't guess intent from natural language. |
| **Task Tracking** | `pending → running → success/failed/timeout`. Full chain tracing. |
| **Priority Queue** | Urgent messages first, with preemption support. |
| **Agent Type Abstraction** | Single config template, 6 frameworks built-in (see below). |
| **Multi-Model Fallback** | Model alias system. Tries models in order, falls through automatically. |
| **Broadcast** | `broadcast` command pushes to all agents at once. |
| **Reminders** | Auto-retry on timeout + escalation notifications. |
| **Heartbeat** | Periodic agent ping. Offline agents skip retry. |
| **Message Search** | SQLite FTS5 full-text index. |
| **Error Reports** | Standardized `error_code/reason/trace` format. |
| **Error Logs** | JSONL format, weekly rotation, auto-cleanup after 30 days. |
| **Memory Sync** | Optional AgentMemory bridge for persistent message history. |
| **Archival** | Acknowledged messages auto-archived after 7 days / 300 messages. |

### Supported Agent Frameworks

| Type | CLI Template | Framework |
|------|-------------|-----------|
| `hermes` | `hermes chat -q 'MSG' -Q` | Hermes Agent |
| `hermes_profile` | `hermes chat -q 'MSG' -Q --profile PROFILE` | Hermes Multi-Profile |
| `openclaw` | `openclaw agent --local --agent AGENT --message 'MSG'` | OpenClaw Gateway |
| `cline` | `cline 'MSG' --provider openai-compatible` | Cline CLI |
| `opencode` | `opencode run 'MSG' --dangerously-skip-permissions MODEL` | OpenCode |
| `none` | File-only communication, no CLI push | Manual dispatch |

> Adding a new framework? Just add one CLI template to `agent_types`. Zero code changes.

### Registered Agents (v2.1.0)

| Agent | Name | Role | Framework |
|-------|------|------|-----------|
| `lingzhao` | 🪷 灵昭 | Solution Design | Hermes |
| `lingjin` | 🦋 灵瑾 | Network Security | Hermes Profile |
| `lingxi` | 🔭 灵犀 | Tech Radar | Hermes Profile |
| `lingtuo` | 🧭 灵拓 | Market Expansion | Hermes Profile |
| `lingjian` | 🔍 灵鉴 | Code Review | Hermes Profile |
| `lingyan` | 🧪 灵验 | Testing & QA | Hermes Profile |
| `lingxun` | 🔦 灵巡 | Patrol & Daily Report | Hermes Profile |
| `lingzhang` | 🧾 灵账 | Billing & Collections | Hermes Profile |
| `xiaoqi` | 🦞 小七 | Dispatch | OpenClaw |
| `yige` | 👨‍🔧 一哥 | Operations & Content | OpenClaw |
| `lingxiao` | 🎯 灵霄 | Tech Lead | Cline CLI |
| `dali` | 🤖 大力 | Coding | OpenCode |

> 💪 大壮 (Code Review, Aider) — 已退役，由灵鉴 + review.py + Semgrep 替代

### Changelog

- **v2.1.0** (2026-06-03) — 🔍 灵鉴 (Code Review), 🧪 灵验 (Testing) joined; version migration system; instant push on API send-message; timeout auto-closed after 3 reminders; all dict field defensive checks in Message.from_dict; security audit fixes (env leak, path traversal); alerter notifies 灵昭 + 小七 with instant push; tracker syncs with inbox state; heartbeat offline notification instant push; test port conflict fixed
- **v1.2.0** (2026-05-22) — 🦋 灵曦 renamed to 灵瑾; 🔭 灵犀 (Tech Radar) joined as Hermes Profile
- **v1.1.0** (2026-05-21) — Multi-model fallback, heartbeat, alerting, Platform v2 UI (tabs + cards)

## CLI Commands

```bash
mailbus init                        # Initialize directory structure
mailbus scan                        # Scan all inboxes → push + heartbeat + reminders + index
mailbus send <agent>                # Send a message (--priority/--type/--forward-to)
mailbus broadcast                   # Broadcast to all agents
mailbus ack --msg-id <ID>           # Agent acknowledges receipt
mailbus mark-read --msg-ids <ID>    # Agent marks messages as read
mailbus status [--agent <name>]     # View message status
mailbus status --failed             # View failed messages
mailbus retry [--msg-id <ID>]       # Retry failed messages
mailbus archive                     # Trigger archival manually
mailbus errors                      # View error logs
mailbus agent-add <name>            # Register a new agent
mailbus agent-remove <name>         # Remove an agent
mailbus heartbeat                   # Heartbeat detection (check all agent online status)
mailbus search                      # Full-text message search
mailbus serve [--host] [--port]      # Start HTTP API server (default 127.0.0.1:9814)
mailbus launch                       # Start all agent processes (Gateways / Dashboards)
mailbus launch --status              # View agent process running status
mailbus launch --stop                # Stop all agent processes
mailbus launch --agent xiaoqi        # Start a specific agent
```

## Platform Web UI

mailbus ships with a standalone web management interface — **ziyan-mailbus Platform**. Zero dependencies, open and use:

```bash
# 1. Start the HTTP API
mailbus serve --host 127.0.0.1 --port 9814 --data-dir /path/to/store

# 2. Open docs/platform.html in your browser (or serve with any static server)
```

**Dashboard sections:**

| Section | Content |
|---------|---------|
| **Overview** | Agent count, total messages, pending count |
| **Agent List** | Name, type, role, model config (dynamically reads config.json) |
| **Task Tracking** | Status, trace chain, reminder count |
| **Heartbeat** | AgentMemory / disk / inbox backlog / per-agent online status |
| **Alerts** | Severity, type, timestamp |
| **Raw JSON** | View raw API response data |

**Controls:**
- 🔄 **Refresh All** — reload all data
- 💓 **Trigger Heartbeat** — run an on-demand agent health check
- Per-section **🔄 Refresh** buttons — refresh individual sections
- **Auto-refresh** — set `dashboard_refresh_seconds` in `config.json`, Platform auto-updates

Platform is completely framework-agnostic. Move to a different environment? Just change the API URL.

## Agent Reply Format

Agents reply to the bus by writing files (not by calling CLI):

**ACK (ack.json):**
```json
{"action":"ack","msg_id":"msg-xxx","agent":"agent-a","timestamp":"2026-05-21T12:00:05+0800"}
```

**Mark as Read (mark.json):**
```json
{"action":"mark_read","msg_ids":["msg-xxx","msg-yyy"],"agent":"agent-a","timestamp":"2026-05-21T12:00:05+0800"}
```

**Forward to Another Agent:**
Write directly to the target agent's `inbox.json` (append to `messages` array + set `has_unread: true`)

## AgentMemory Bridge (Optional)

mailbus can automatically sync acknowledged messages to [AgentMemory](https://github.com/AgentMemory/AgentMemory), ensuring agents can retrieve message history after restart.

```bash
# Ensure AgentMemory is running at http://localhost:3111
# Chain in cron:
* * * * * cd /path/to/ziyan-mailbus && mailbus scan && python3 mailbus-memory-bridge.py --data-dir /path/to/store
```

Messages stored with tags: `[agent:xxx] [from:yyy] [msg_id:zzz] <message content>`

## Multi-Model Fallback

Each agent can be configured with multiple LLM model aliases. The bus tries them in order and stops at the first successful one:

```json
{
  "agents": {
    "agent-b": {
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

Use the `MODEL` placeholder in CLI templates; the bus resolves it from the agent's model alias list.

## Configuration Reference

Full example config at [examples/config.example.json](examples/config.example.json).

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
      "role": "Description",
      "type": "hermes",
      "models": ["deepseek-chat"],
      "inbox": "/path/to/your/store/inbox/agent-a/inbox.json"
    }
  },
  "agent_types": {
    "hermes": {
      "push": "hermes chat -q 'MSG' -Q",
      "description": "Hermes Agent"
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

## Project Structure

```
ziyan-mailbus/
├── bus.py                        # CLI entry point
├── mailbus-boot.sh                # Full startup script (launches bus.py + all agent processes)
├── lib/
│   ├── __init__.py
│   ├── models.py                 # Data models (Message, Inbox, MsgType)
│   ├── scanner.py                # Inbox scanning → queue building
│   ├── pusher.py                 # CLI push + multi-model fallback
│   ├── ack_handler.py            # Agent reply handling
│   ├── archiver.py               # Message archival
│   ├── tracker.py                # Task tracking + reminders
│   ├── heartbeat.py              # Heartbeat + health monitoring
│   ├── search.py                 # SQLite FTS5 full-text search
│   ├── alerter.py                # Alert system
│   ├── api_server.py             # HTTP API server
│   └── utils.py                  # File lock, JSON I/O, message builder
├── mailbox-daemon.py             # Agent-side daemon (v0.5: task tracking + batch + dedup)
├── mailbus-memory-bridge.py      # AgentMemory bridge (optional)
├── store/                        # Runtime data (gitignored)
├── tests/                        # Test suite (10 files, 90+ tests)
├── docs/
│   ├── platform.html             # Web management UI
│   ├── architecture-v2.html      # Architecture diagram
│   ├── quickstart.md
│   └── message-format.md
├── examples/
│   └── config.example.json       # Clean example config
├── ARCHITECTURE.md
├── README.md
├── README.zh.md
├── CHANGELOG.md
├── LICENSE
└── pyproject.toml
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md).

## Contributing

ziyan-mailbus aims to achieve true **A2A (Agent-to-Agent)** communication — breaking down the barriers between different AI agent frameworks.

Whether you use Hermes, OpenClaw, Cline, OpenCode, Aider, or any other AI agent framework — mailbus makes them talk to each other seamlessly.

Contributions welcome:
- **File an Issue** — bug reports, feature requests
- **Submit a PR** — bug fixes, new framework support
- **Share your story** — how you use mailbus with your agent team

## License

MIT License — see [LICENSE](LICENSE).

Copyright (c) 2026 子言·塔罗
