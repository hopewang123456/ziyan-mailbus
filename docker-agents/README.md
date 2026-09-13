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
| Start | `pip install -e ..` then `mailbus start` |

`docker-compose.yml` mounts **mailbus repo** paths (`../skills`, …) and `${ENV}` for agent homes. Unset env falls back to empty `./workspaces/*` placeholders — **not** sibling `../openclaw_space` or `../../Agent/docker`. Point `.env` at your real Agent trees; that is config association, not layout coupling.

`tools/mailbus.py` is the canonical entry (`python tools/mailbus.py start`); thin wrappers are `scripts/start-mailbus.bat` / `scripts/start-mailbus.sh`.

See [`../README.md`](../README.md) (EN) · [`../README.zh.md`](../README.zh.md) (ZH) · [`../docs/migration-guide.md`](../docs/migration-guide.md).
