# lib.application.harness

Agent harness contract / production / report API / verify escalation.

## Role

Spawn agents, wait for completion, report / escalate.

## Dependency direction

→ `interfaces` / `domain`; test fixtures in `tests/harness_fixtures/`

## Forbidden imports

Prefer not importing concrete `adapters.frameworks` from non-production paths

## Files

| File | Purpose |
|------|---------|
| `contract.py` | Harness contract types |
| `production.py` | Production harness |
| `report_api.py` | Report API |
| `escalation.py` | Escalation helpers |
