# lib.adapters.frameworks

Agent framework registry/support and `direct_push` (formerly `lib.agent_push`).

## Role

Framework plugins (Hermes, OpenClaw, Codex, Claude, …) and push helpers.

## Dependency direction

`interfaces.AgentRuntimePort` ← this package; discovered via entry points

## Forbidden imports

`lib.application.*` (application must not import these concretes)

## Files

| File | Purpose |
|------|---------|
| `registry.py` | Framework registry |
| `direct_push.py` | Direct CLI push |
| `entry_point_discovery.py` | Plugin load |
