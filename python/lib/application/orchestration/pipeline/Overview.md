# lib.application.orchestration.pipeline

FSM-driven step advancement (chain / routing / results / trigger).

## Role

Advance pipeline tasks: trigger steps, route roles, check/write results, work orders.

## Dependency direction

→ `lib.interfaces` · `lib.domain` · `lib.core.a2a` · `lib.composition`  
← `lib.api` · orchestration mediator / tracker

## Forbidden imports

`lib.adapters.*` (use composition / ports)

## Files

| File | Purpose |
|------|---------|
| `trigger.py` | FSM trigger (stays here; not under workflow/) |
| `chain.py` | Chain helpers |
| `step.py` | Step helpers / `is_role_pipeline_task` |
| `results.py` | Result I/O |
| `routing.py` | Role routing |
| `task.py` | Task helpers |
| `work_order.py` | Work-order shaping |
| `result_check.py` | Result verification |
