# Mailbus Architecture (Python service)

## Layers

```
core  →  application  →  adapters  →  api  →  bootstrap
```

- `core`: domain models and rules. No IO, no third-party imports, no clock
  or UUID calls. State enums live only here (guard G7).
- `application`: one use case = one SQLite unit of work. State changes and
  outbox rows commit together. All writes call
  `core.identity.policy.ensure_allowed` first.
- `adapters`: SQLite repositories and migrations, outbox dispatcher
  transports (A2A, MCP pull, file bus), system clock and id generator.
- `api`: protocol translation only. Routers resolve the caller through
  `deps.get_actor` and never implement permission rules.
- `bootstrap`: settings, container wiring, lifespan and background tasks.
  Filesystem paths appear only here.

## Guards

`python/tests/guards/` enforces the rules:

- G1 layer imports (API may only import `core.shared`)
- G2 core imports standard library only
- G3 file ≤ 400 lines, function ≤ 50 lines
- G4 router functions ≤ 25 lines
- G5 generated OpenAPI contract matches code
- G6 repository hygiene (root whitelist, no runtime data in git)
- G7 state constants only in `core`
- G8 write routes declare `__mailbus_capability__`

## Runtime

- SQLite with WAL; one connection per unit of work.
- The dispatcher polls the outbox with exponential backoff and stops after
  `MAILBUS_DISPATCH_MAX_ATTEMPTS` (default 3) failures.
- `file_bus` inbound files are scanned by a background loop and enter the
  same `MessagingService.send` path as A2A and MCP HTTP entry points.

## Contract

Code is the source of truth. Export with
`python tools/export_openapi.py`; the result is committed under
`shared/contracts/generated/openapi.json` and checked by G5.
