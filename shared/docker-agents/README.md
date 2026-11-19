# docker-agents

mailbus Docker full-agent stack (compose SoT in this directory).

| Item | Path |
|------|------|
| Source | `../..` (mailbus repo root) |
| `MAILBUS_DATA` | `../data` (SQLite + file_bus / MCP queues) |
| Compose env sample | [`.env.example`](.env.example) → copy to `.env` |
| Agent homes | `.env` absolute paths (`OPENCLAW_WORKSPACE`, …); see [`workspaces/README.md`](workspaces/README.md) |
| Local overrides | `docker-compose.override.yml` (gitignored; copy from `docker-compose.override.example.yml`) |

## Quick start

```bash
cd shared/docker-agents
cp .env.example .env
docker compose up -d --build
```

The `mailbus` service runs `uvicorn mailbus.bootstrap.main:app` on port 9814;
health check: `http://127.0.0.1:9814/api/health`.

`docker-compose.yml` mounts **mailbus repo** paths (`../skills`, …) and `${ENV}` for agent homes. Unset env falls back to empty `./workspaces/*` placeholders — not sibling-repo relative defaults. Point `.env` at your real Agent trees; that is config association, not layout coupling.

Agent containers still follow their own framework entrypoints; the mailbus
service itself is the new FastAPI app described above.

See [`../README.md`](../README.md) (EN) · [`../README.zh.md`](../README.zh.md) (ZH).
