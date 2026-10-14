# lib.adapters.integrations.n8n

n8n bridge adapter (incl. WSL fallback).

## Role

POST JSON to n8n webhooks; WSL/host fallback for Windows.

## Dependency direction

→ network / WSL helpers  
← IntegrationsPort / workflow drill

## Forbidden imports

`lib.application.*`

## Files

| File | Purpose |
|------|---------|
| `wsl_bridge.py` | POST JSON with WSL fallback |
| `url_resolve.py` | Resolve n8n base URL |
| `__init__.py` | Package exports |
