# lib.api

Thin HTTP handlers. Depend on application + interfaces; composition for adapter wiring.

## Role

Route HTTP → use cases. Error JSON always includes `error_code` + `message_zh` (via `_send_json` / `_send_api_error`).

## Dependency direction

→ `lib.application` · `lib.interfaces` · `lib.domain` · `lib.composition`  
← `bus` / serve entry

## Forbidden imports

Deep `lib.adapters.frameworks.*` in handlers when avoidable (prefer composition).

## Files

| File | Purpose |
|------|---------|
| `base.py` | Auth, routing, `_send_json` / `_send_api_error` |
| `handlers_*.py` | Domain handlers |
| `internal_llm_status.py` | Internal LLM status helper |
