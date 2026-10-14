# lib.domain

Domain DTOs, error types, and FSM primitives.

## Role

Shared immutable types (`AgentRef`, `OutboundMessage`, `TransportReceipt`, error codes).

## Dependency direction

Leaf-ish: must not import application / adapters / api / interfaces implementations

## Forbidden imports

`lib.application.*`, `lib.adapters.*`, `lib.api.*`, `lib.composition`

## Files

| File | Purpose |
|------|---------|
| `types.py` | Core DTOs |
| `error_codes.py` | Stable error codes |
| (package exports) | `Fatal`, `Retryable`, `BudgetPaused`, … |
