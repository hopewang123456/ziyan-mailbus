# lib.adapters.ops

Operational adapters (heartbeat, alerter, doctor, scheduler, jobs, clinic).

## Role

Implement `OpsPort`. Wave 2 ships a facade over root `lib.heartbeat` / `lib.alerter` /
`lib.doctor_checks` / `lib.scheduler` / `lib.jobs` / `lib.clinic_tools` until those
modules fully relocate here.

## Dependency direction

`interfaces.OpsPort` ← this package → root ops modules / `infra`

## Forbidden imports

`lib.application.*`

## Files

| File | Purpose |
|------|---------|
| `facade.py` | `RootOpsAdapter` / `build_ops` |
| `__init__.py` | package exports |
