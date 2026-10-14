# lib.adapters.discovery

Agent discovery sources (dir / docker / env).

## Role

Implement `DiscoverySource` variants used by composition `AppContext.discovery_sources`.

## Dependency direction

`interfaces.discovery` ← this package → filesystem / docker / env

## Forbidden imports

`lib.application.*`

## Files

| File | Purpose |
|------|---------|
| `__init__.py` | `DirDiscoverySource` / `DockerDiscoverySource` / `EnvDiscoverySource` / `build_default_sources` |
