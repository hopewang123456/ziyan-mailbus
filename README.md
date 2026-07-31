# ziyan-mailbus

File-based **Agent-to-Agent** message bus. Framework-agnostic: Hermes, OpenClaw, Codex, OpenCode, Claude Code, and more via adapters.

No Redis / RabbitMQ required — messages are JSON files, CLI push, agent ack.

## Requirements

- Python ≥ 3.10
- Optional: Docker, Ollama (local routing), AgentMemory
- At least one agent CLI or a remote A2A endpoint

## Quick start

```bash
git clone https://github.com/hopewang123456/ziyan-mailbus.git
cd ziyan-mailbus
pip install -e .

# Init store (creates store/config.json from seeds + demo agents)
mailbus init --data-dir ./store

# Or merge after editing templates
mailbus init --merge --data-dir ./store

# Serve API + built-in scheduler (default port 9814)
mailbus serve --host 0.0.0.0 --port 9814 --data-dir ./store

# Send a message (demo agents from examples/)
mailbus send agent-a --msg "Hello" --from agent-b --data-dir ./store
mailbus status --data-dir ./store
```

Copy [`migrate/env.template`](migrate/env.template) → `.env` and set keys / paths. **Never commit `.env`.**

### LLM / Ollama

On first start mailbus prefers your local Ollama models (first listed model if none configured).  
If neither Ollama nor a cloud API key is available, the dashboard prompts you to configure one.

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

#### Deployment differences

| | **Linux / macOS (native)** | **Windows + WSL team stack** |
|--|----------------------------|------------------------------|
| Day-to-day start | `python tools/mailbus.py start` or `mailbus serve` | Same Python entry; optional thin `.bat` under `scripts/` / `tools/mailbus/` |
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

## Demo agents (T1)

Published examples use generic ids (`agent-a`, `agent-b`, `agent-c`).  
See [`examples/demo-roster.json`](examples/demo-roster.json) and [`examples/config.example.json`](examples/config.example.json).

Register your own agents in the cockpit **Settings** (enable is off by default after auto-discovery).

## Cockpit

Open `http://127.0.0.1:9814/` after `mailbus serve`.  
Legacy UI: `/legacy` if present.

## Docs

- Adapter layer: `docs/agent-adapter-layer.md` (when shipped in-repo)
- Harness: `docs/harness-runtime-spec.md`
- Env template: `migrate/env.template`

## License

MIT
