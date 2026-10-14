# lib.application.scan

Inbox scanning, queues, housekeeping (formerly `lib.scan`).

## Role

Periodic inbox / queue maintenance use cases.

## Dependency direction

→ `domain`, `core.a2a` poll helpers, orchestration triggers

## Forbidden imports

`lib.adapters.frameworks.*`

## Files

| File | Purpose |
|------|---------|
| `inbox.py` | Inbox scan |
| `queues.py` | Queue maintenance |
| `housekeeping.py` | Housekeeping |
