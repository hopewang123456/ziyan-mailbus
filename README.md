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

# 4. Start the bus (cron, scans every minute)
crontab -e
# Add: * * * * * cd /path/to/ziyan-mailbus && mailbus scan

# 5. Send a message
mailbus send agent-a --msg "Hello, please handle this task" --from lingzhao
mailbus broadcast --msg "System maintenance notice"

# 6. Check status
mailbus status
mailbus status --failed
```

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

### Registered Agents (v1.2.0)

| Agent | Name | Role | Framework |
|-------|------|------|-----------|
| `lingzhao` | 🪷 灵昭 | Solution Design | Hermes |
| `lingjin` | 🦋 灵瑾 | Network Security | Hermes Profile |
| `lingxi` | 🔭 灵犀 | Tech Radar | Hermes Profile |
| `xiaoqi` | 🦞 小七 | Dispatch | OpenClaw |
| `yige` | 👨‍🔧 一哥 | Operations | OpenClaw |
| `lingxiao` | 🦅 灵霄 | Tech Lead | Cline CLI |
| `dali` | 🤖 大力 | Coding | OpenCode |
| `dazhuang` | 💪 大壮 | Code Review | File-only |

### Changelog

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
mailbus serve [--port]              # Start HTTP API server (default port 9812)
```

## Platform Web UI

mailbus ships with a standalone web management interface — **ziyan-mailbus Platform**. Zero dependencies, open and use:

```bash
# 1. Start the HTTP API
mailbus serve --port 9812 --data-dir /path/to/store

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
