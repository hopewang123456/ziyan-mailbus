# lib.adapters.orchestration

Concrete FSM, budget, notifier, human-gate, audit adapters.

## Role

Implement orchestration-related ports (`TaskFsmPort`, `BudgetMeterPort`, `NotifierPort`, gates).

## Dependency direction

`interfaces` ← this package → `domain` / store files

## Forbidden imports

`lib.application.*`

## Files

Plan D20 kept these adapter modules (pipeline.py shell removed). Current set:

| File | Purpose |
|------|---------|
| `audit.py` | JSONL audit |
| `automation.py` | Retry / auto-approve policy |
| `budget.py` | Daily budget FSM |
| `complexity_router.py` | L0–L3 smart routing |
| `fsm.py` | Thin `TaskFsmPort` adapter |
| `human_gate.py` | HumanGateAdapter |
| `human_queue.py` | human-queue.json I/O |
| `notifier.py` | JSONL notifier |
| `phantom_detect.py` | Phantom receipt detect |
| `task_fsm.py` | Task FSM + `apply_resume` / `bump_retry` |
| `__init__.py` | builders |
