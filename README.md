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
