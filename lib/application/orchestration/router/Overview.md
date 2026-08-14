# lib.application.orchestration.router

Plan approval and dispatch routing.

## Role

Planner auto-approve policy + dispatch routing for orchestration.

## Dependency direction

→ `lib.composition` · `lib.interfaces`  
← mediator / pipeline

## Forbidden imports

`lib.adapters.*`

## Files

| File | Purpose |
|------|---------|
| `planner.py` | Plan approval helpers |
| `dispatch.py` | Dispatch routing |
