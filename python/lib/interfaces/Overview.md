# lib.interfaces

Protocol / Port interfaces for Mailbus (formerly `lib.ports`).

## Role

Define structural contracts consumed by `lib.application` and implemented by `lib.adapters`.

## Dependency direction

- May import `lib.domain` (DTOs only)
- Must **not** import `application`, `adapters`, `api`, or `infra` concretes

## Forbidden imports

`lib.application.*`, `lib.adapters.*`, `lib.api.*`, root ops modules used as implementations

## Files

| File | Ports |
|------|--------|
| `message_transport.py` | `MessageTransportPort`, `A2ATransportPort`, `BridgedAgentPort` |
| `ops.py` | `OpsPort` |
| `integrations.py` | `IntegrationsPort` |
| `locale.py` | `LocalePort` (`get`/`load`/`message_zh`/role helpers) |
| `runtime.py` | `AgentRuntimePort` |
| `clock.py` | `Clock`, `IdGenerator`, `PathRoot` |
| `config_repo.py` | `ConfigRepository` |
| `discovery.py` | `DiscoverySource` |
| `gates.py` | `AuditPort`, `HumanGatePort` |
| `orchestration.py` | `TaskFsmPort`, `BudgetMeterPort`, `NotifierPort`, … |
| `plane.py` | Host/Container/Mount ports |
| `results.py` | `ResultStorePort` |
| `auth.py` | `AuthPort` |
