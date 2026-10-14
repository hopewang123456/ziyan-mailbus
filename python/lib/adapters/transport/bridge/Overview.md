# lib.adapters.transport.bridge

CLI / file-bus bridge for non-A2A agents (`BridgedAgentPort`).

## Role

Provide a unified send/cancel/status path for agents that use inbox + ack.json
instead of Google A2A JSON-RPC.

## Dependency direction

`interfaces` ← this package → `adapters.transport.file_bus`, `adapters.results`, `domain`

## Forbidden imports

`lib.application.*` (except future composition-bound harness if needed)

## Files

| File | Purpose |
|------|---------|
| `cli_bridge.py` | `CliBridgedAgent` implementing `BridgedAgentPort` |
| `lifecycle_rules.py` | Exit-code map, timeout, retry helpers |
