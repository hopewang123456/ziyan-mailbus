# mailbus

Agent message bus built with layered FastAPI + SQLite, plus a shared React
cockpit (`web/`).

The Python service is a layered FastAPI application backed by SQLite:
domain rules in `mailbus/core`, use cases in `mailbus/application`,
adapters in `mailbus/adapters`, HTTP mapping in `mailbus/api`, and
composition in `mailbus/bootstrap`. Runtime data lives under `data/`
(override with `MAILBUS_DATA_DIR`).

## Quick start

```bash
cd python
pip install -e ".[dev]"
uvicorn mailbus.bootstrap.main:app --port 9814
```

- Health: `GET http://127.0.0.1:9814/api/health`
- OpenAPI: `GET http://127.0.0.1:9814/api/openapi.json`
- Tests: `python -m pytest -q`
- Contract export: `python tools/export_openapi.py`

Log in through `POST /api/identity/bootstrap/super-admin` on first run.

## Java backend

`java/` mirrors the Python service with Spring Boot 3.3 / JDK 17 and matches the
OpenAPI contract in `shared/contracts/generated/openapi.json` (83 paths / 104
operations). It shares the SQLite schema and `data/` directory, so teams without
Python experience can build on it directly:

```bash
cd java
mvn spring-boot:run
```

See [java/README.md](java/README.md) for configuration and extension notes.

## Layout

| Directory | Contents |
|---|---|
| `python/` | Python service (`mailbus` package, tests, contract export) |
| `java/` | Java service (Spring Boot 3.3, same contract as Python) |
| `web/` | React cockpit |
| `shared/` | Language-neutral assets and generated contracts |
| `config/` | Static seed data (office layout) |
| `data/` | Runtime state: SQLite database, file-bus and MCP queues |
| `docs/` | Product and design documents |

## Layering

```
core → application → adapters → api → bootstrap
```

- `core` is pure domain logic (standard library only).
- `application` owns one transaction per use case and the outbox.
- `adapters` implement persistence, transport, clock and ids.
- `api` only translates HTTP and resolves the caller.
- `bootstrap` is the only place that knows filesystem paths.

All permission checks go through `core.identity.policy.ensure_allowed`;
write routes must declare a capability so guard G8 can verify them.

The old Python stack (`python/lib`, `python/bus`, old `python/tools/`) was
removed in the B7 cleanup.
