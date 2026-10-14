# lib.core

Framework-agnostic core protocol code.

## Role

Host protocol engines that are neither application use-cases nor I/O adapters.

## Dependency direction

→ `domain`, `infra` (clock/utils); ← used by `application` / `adapters.transport`

## Forbidden imports

`lib.application.*` (prefer thin callbacks), `lib.api.*`

## Files

| Path | Purpose |
|------|---------|
| `a2a/` | Google A2A transport stack |
