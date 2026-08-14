# lib.application.queries

CQRS read-side helpers (active agents, chain budget views, etc.).

## Role

Query/read models for cockpit and CLI — no write-side orchestration.

## Dependency direction

→ `lib.interfaces` · `lib.domain` · `lib.infra`  
← `lib.api` · `lib.composition` · tools

## Forbidden imports

`lib.adapters.frameworks.*` concrete modules (use composition / ports)

## Files

| File | Purpose |
|------|---------|
| `__init__.py` | Package exports |
| (module files) | Read-side query helpers |
