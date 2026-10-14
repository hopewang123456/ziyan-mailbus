# lib.application.orchestration

Pipeline dispatch, routing, failover, execution, step dispatch.

## Role

Core orchestration use cases (task FSM transitions via ports, role resolve, work orders).

## Dependency direction

→ `interfaces`, `domain`, `core.a2a`; bind adapters via `composition`

## Forbidden imports

`lib.adapters.frameworks.*` concrete modules; `lib.adapters.orchestration.task_fsm` (use composition/`get_fsm`)

## Files

| Path | Notes |
|------|--------|
| `actions.py` | Orchestration actions |
| `execution.py` | Step execution helpers |
| `step_dispatch.py` | Dispatch entry |
| `dispatch/` | Role resolver, failover |
| `pipeline/` | Trigger, routing, task, work_order, result_check |
| `router/` | Planner |
