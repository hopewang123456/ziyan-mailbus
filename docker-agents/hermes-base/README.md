# Hermes base image — ops helpers

Build/runtime (tracked): `Dockerfile`, `entrypoint.sh`, `sync-identities.sh`.

## Stable host scripts (this directory)

Prefer `SCRIPT_DIR` / `HERMES_DATA` / `docker-agents/.env` — **no** hard-coded `ai_tools` layout.

| Script | Purpose |
|--------|---------|
| `check-hermes-ready.sh` / `wait-hermes-ready.sh` | Probe container readiness |
| `find-hermes-volume.sh` | Inspect mounts / HERMES_DATA |
| `migrate-hermes-data-dir.sh` / `finish-hermes-data-migrate.sh` | Move Hermes home → `HERMES_DATA` |
| `ensure-memos.sh` / `wire-memos.sh` | MemOS ensure / wire |
| `run-memos-install-host.sh` | `docker cp` + exec `install-memos-in-container.sh` |
| `install-memos-in-container.sh` | In-container MemOS installer |

Also: repo `docker-agents/migrate-hermes-home-to-e.sh` (requires `HERMES_DATA` + `HERMES_OLD_HOME`).
Compose workspaces: `../workspaces/README.md`.

## Scratch (gitignored)

One-off debug / rebuild helpers live under `scratch/` and are **not** part of the product surface.
