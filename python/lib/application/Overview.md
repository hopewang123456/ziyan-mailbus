# lib.application

Use-case layer: orchestration, workflow, harness, scan, push, internal LLM planning, ops.

## Role

Business flows; depends on ports, not concrete adapter modules (except legacy allowances).

## Dependency direction

→ `interfaces`, `domain`, `core`; ← `api` / `tools` / `composition`

## Forbidden imports

Concrete `adapters.frameworks.*` (bind via composition); prefer not importing `adapters.ops` facades directly long-term

## Packages

| Package | Role |
|---------|------|
| `harness/` | Contract / production harness |
| `orchestration/` | Pipeline / dispatch |
| `workflow/` | Engine, intake, drill |
| `scan/` | Inbox / queues / housekeeping |
| `push/` | Push with contract |
| `ops/` | Cleanup, gates, verify |
| `internal_llm/` | Triage / planner / budget |
