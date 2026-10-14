# lib.adapters.fakes

Test doubles for ports (runtime, transport, ops, etc.).

## Role

In-memory / stub adapters for unit tests and dry-run.

## Dependency direction

`interfaces` ← this package; used by `tests/` / composition dry-run

## Forbidden imports

Production side-effects, Docker, live network

## Files

| File | Purpose |
|------|---------|
| `runtime.py` | Fake agent runtime |
| `result_store.py` | Fake result store |
| `transport.py` | FakeA2ATransport / FakeMessageTransport |
| `bridged.py` | FakeBridgedAgent |
| `ops.py` | FakeOps |
| `integrations.py` | FakeIntegrations |
| `__init__.py` | exports |
