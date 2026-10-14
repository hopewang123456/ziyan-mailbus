# lib.infra

Cross-cutting infra: clock, internal LLM process ensure/startup.

## Role

Shared low-level helpers (time, process bootstrap). Target home for `constants`/`utils` in later waves.

## Dependency direction

Leaf: used by all layers; must not import `application` / `adapters` / `api`

## Forbidden imports

`lib.application.*`, `lib.adapters.*`, `lib.api.*`, `lib.composition`

## Files

| Path | Purpose |
|------|---------|
| `clock.py` | System/fake clock, path root, ids |
| `internal_llm/` | Ollama ensure / startup |
