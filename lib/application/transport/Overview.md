# lib.application.transport

Transport use-case helpers (delivery normalization).

## Role

Application-side normalization around A2A / file-bus receipts before orchestration consumes them.

## Dependency direction

→ `interfaces` / `core.a2a` / `composition` ← orchestration / API

## Forbidden imports

Direct `adapters.transport.*` (use composition `build_transport`)

## Files

| File | Purpose |
|------|---------|
| `delivery_normalizer.py` | Normalize delivery / step-result paths via FSM port |
| `__init__.py` | package exports |
