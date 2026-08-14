# docker-agents

mailbus Docker full-agent stack (compose SoT in this directory).

| Item | Path |
|------|------|
| Source + store | `../` (mail repo root) |
| `MAILBUS_DATA` | `../store` |
| Env template | [`../migrate/env.template`](../migrate/env.template) |
| Local Vault binds | `docker-compose.override.yml` (gitignored; copy from `override.example.yml`) |
| Start | `pip install -e ..` then `mailbus start` |

`docker-compose.yml` uses **repo-relative** mounts (`../skills`, …) and `${ENV}` for external homes (`HERMES_DATA`, `OPENCLAW_WORKSPACE`, `OPENCODE_ROOT`, `CODEX_WORKSPACE`, `CODEX_SKILLS`, `NODE_MODULES`, `TEAM_PACK_ROOT`). Do not put host Vault absolute paths in the committed compose file.

`tools/mailbus.py` is the canonical entry (`python tools/mailbus.py start`); thin wrappers are `scripts/start-mailbus.bat` / `scripts/start-mailbus.sh`.

See [`../README.md`](../README.md) (EN) · [`../README.zh.md`](../README.zh.md) (ZH) · [`../docs/migration-guide.md`](../docs/migration-guide.md).
