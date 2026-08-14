# lib.application.push

Application-level push orchestration helpers.

## Role

Push-with-contract and related application flows. Direct CLI push adapter lives in `lib.adapters.frameworks.direct_push`.

## Dependency direction

→ `interfaces` / harness / message transport ports

## Forbidden imports

Prefer composition-bound adapters over direct framework imports (legacy allowances exist)

## Files

| File / package | Purpose |
|----------------|---------|
| `__init__.py` | package |
| (related) `push_with_contract.py` at application root | Contract push |
