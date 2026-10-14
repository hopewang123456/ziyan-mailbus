# lib.application.ops

Operational use cases (cleanup, e2e gates, verify runners, watchdogs).

## Role

Ops *use cases* (not the OpsPort facade — that is `adapters.ops`).

## Dependency direction

→ `interfaces`, `domain`; may call jobs helpers during transition

## Forbidden imports

`lib.adapters.frameworks.*`

## Files

| Path | Purpose |
|------|---------|
| `e2e_gates.py` / `platform_scout.py` / `store_cleanup.py` | Ops use cases |
| `pipeline_watchdog.py` / `self_heal.py` / `repair_pipeline.py` | Watchdogs |
| `verify/` | Harness / deliverable / git checks |
