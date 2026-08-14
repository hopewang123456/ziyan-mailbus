# lib.adapters.results

Result store and ack / forward file scanners.

## Role

Implement `ResultStorePort` (file-backed) and scan helpers for ack / error reports.

## Dependency direction

`interfaces.results` ← this package → `store/` filesystem

## Forbidden imports

`lib.application.*` (except documented harness callers)

## Files

| File | Purpose |
|------|---------|
| `msg_results.py` | `FileResultStore` |
| `ack.py` | Ack helpers |
| `ack_handler.py` | Scan ack / forward / error report files |
| `__init__.py` | package exports |
