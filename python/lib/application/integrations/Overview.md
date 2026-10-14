# lib.application.integrations

Integration use-cases (token-budget driven scan intervals).

## Role

Application policies on top of `IntegrationsPort` (not concrete plugin I/O).

## Dependency direction

→ `interfaces.integrations` / `composition` ← scan / orchestration

## Forbidden imports

`adapters.integrations.*` directly (use `get_integrations()`)

## Files

| File | Purpose |
|------|---------|
| `token_budget.py` | Token-driven dynamic scan interval |
| `__init__.py` | package exports |
