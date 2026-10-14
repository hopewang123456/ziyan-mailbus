# lib.adapters.container

Container/Codex/OpenClaw profile helpers and privilege path mapping.

## Role

Container-plane helpers for agent homes and privilege paths.

## Dependency direction

Used by plane / lifecycle; → store / docker helpers

## Forbidden imports

`lib.application.*`

## Files

| File | Purpose |
|------|---------|
| `resolver.py` | `resolve_container` / `container_prefix` / `container_for_service` |
| `codex_config.py` | Codex container config |
| `openclaw_profiles.py` | OpenClaw profiles |
| `privilege.py` | Privilege path mapping |
