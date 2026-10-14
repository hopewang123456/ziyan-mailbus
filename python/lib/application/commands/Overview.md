# lib.application.commands

CLI command use-cases (`mailbus` subcommands).

## Role

Orchestrate init / scan / push / doctor / etc. Bind adapters only via `lib.composition` (target); legacy direct imports being retired in Wave 3.

## Dependency direction

→ `interfaces` / `domain` / `core` / `composition` ← `bus/` CLI

## Forbidden imports

Concrete `adapters.frameworks.*` long-term; prefer composition facades

## Files

| File | Purpose |
|------|---------|
| `commands.py` | Main CLI command implementations |
| `__init__.py` | package exports |
