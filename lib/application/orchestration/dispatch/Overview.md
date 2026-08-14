# lib.application.orchestration.dispatch

Step dispatch and role failover.

## Role

Dispatch a pipeline step to an agent; handle role failover / retries.

## Dependency direction

→ `lib.interfaces` · `lib.composition` · `lib.domain`  
← pipeline / mediator

## Forbidden imports

`lib.adapters.*`

## Files

| File | Purpose |
|------|---------|
| `role_resolver.py` | Resolve role → agent |
| `pipeline_step_failover.py` | Failover when a step cannot run |
