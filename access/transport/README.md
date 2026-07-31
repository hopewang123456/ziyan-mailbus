# Per-agent transport (local)

Runtime loads **`access/transport/<agent_id>/transport.json` only** (not `*.example.json`).

Personal agent folders are **gitignored**. Published demos:

- [`examples/transport/agent-a/`](../../examples/transport/agent-a/)
- [`examples/transport/agent-coder/`](../../examples/transport/agent-coder/) — coding-style agent
- [`examples/transport/agent-chat/`](../../examples/transport/agent-chat/) — chat/gateway-style agent

## Setup

```bash
mkdir -p access/transport/my-agent
cp examples/transport/agent-coder/transport.json access/transport/my-agent/transport.json
# edit agent_id, workspace, docker — then add config/agents/my-agent.override.json
```

See [`config/README.md`](../../config/README.md).
