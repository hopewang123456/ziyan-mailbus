# docker-agents

mailbus Docker full-agent stack (compose SoT in this directory).

| Item | Path |
|------|------|
| Source + store | `../` (mailbus root) |
| `MAILBUS_DATA` | `../store` |
| Compose env sample | [`.env.example`](.env.example) → copy to `.env` |
| Repo-root env | [`../migrate/env.template`](../migrate/env.template) / [`../config/env.template`](../config/env.template) |
| Agent homes | `.env` absolute paths (`OPENCLAW_WORKSPACE`, …); see [`workspaces/README.md`](workspaces/README.md) |
| Local overrides | `docker-compose.override.yml` (gitignored; copy from `docker-compose.override.example.yml`) |

## Quick start

```bash
cd docker-agents
cp .env.example .env
# optional local volume remap:
# cp docker-compose.override.example.yml docker-compose.override.yml
# edit .env: MAILBUS_HOST_ROOT + absolute HERMES_DATA / OPENCLAW_WORKSPACE / …
pip install -e ..
mailbus start   # or: python ../tools/mailbus.py start
```

`docker-compose.yml` mounts **mailbus repo** paths (`../skills`, …) and `${ENV}` for agent homes. Unset env falls back to empty `./workspaces/*` placeholders — not sibling-repo relative defaults. Point `.env` at your real Agent trees; that is config association, not layout coupling.

Thin wrappers: `scripts/start-mailbus.bat` / `scripts/start-mailbus.sh`.

See [`../README.md`](../README.md) (EN) · [`../README.zh.md`](../README.zh.md) (ZH) · [`../migrate/README.md`](../migrate/README.md).
