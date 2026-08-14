# lib.application.workflow

Workflow engine, registry, LLM route. Subpackages: `intake/`, `drill/`.

## Role

Workflow definitions and intake/drill use cases.

## Dependency direction

→ `interfaces`, `domain`; bind transports via composition

## Forbidden imports

`lib.adapters.frameworks.*` concretes

## Files

| Path | Purpose |
|------|---------|
| `engine.py` / `registry.py` / `llm_route.py` | Core workflow |
| `intake/` | Gates, spawn rules, store, task bridge |
| `drill/` | Video publish drill |
