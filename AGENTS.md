# AGENTS.md — Mailbus entry for coding agents

## Product

**mailbus**: agent-to-agent message bus built with layered FastAPI + SQLite,
plus a shared React cockpit (`web/`).

## Repository map

| Path | Role |
|------|------|
| `python/mailbus/` | Python service (layered FastAPI + SQLite) |
| `python/tests/` | guards, e2e and integration tests |
| `python/tools/export_openapi.py` | exports the HTTP contract |
| `java/` | Java service (Spring Boot 3.3, same HTTP contract) |
| `web/` | Cockpit (React) |
| `config/` | Static seed data (office layout) |
| `data/` | Runtime state (SQLite, file-bus / MCP queues), gitignored |
| `shared/` | Language-neutral assets and generated contracts |
| `docs/` | Product and design documents |

## Python dependency rule

```
core → application → adapters → api → bootstrap
```

- `core`: pure domain (standard library only, no clock/UUID/IO).
- `application`: one use case per SQLite unit of work; outbox in the same transaction.
- `adapters`: persistence, transports, clock, ids.
- `api`: protocol translation only; resolves the caller, no permission rules.
- `bootstrap`: the only layer that knows filesystem paths.

Permissions: every write use case starts with
`core.identity.policy.ensure_allowed`. Write routes must declare a capability
(guard G8).

## How to work

1. Read `python/ARCHITECTURE.md` and the target architecture plan in the Vault.
2. Keep changes inside `python/`, `shared/contracts/generated/`, `config/`;
   do not edit `web/` for Python tasks.
3. Run targeted tests first: `python -m pytest tests/guards tests/e2e tests/integration -q`.
4. Re-export the contract after API changes: `python tools/export_openapi.py`.
5. Never commit `.env` / secrets / runtime data under `data/`.

## Quick commands

```bash
cd python
pip install -e ".[dev]"
uvicorn mailbus.bootstrap.main:app --port 9814
python -m pytest -q
python tools/export_openapi.py
```
