# lib.adapters.plane

Host / container execution planes and mount mutex.

## Role

Concrete `HostPlanePort` / `ContainerPlanePort` / `MountMutex` for agent process lifecycle and volume mounts.

## Dependency direction

`interfaces.plane` ← this package → docker/host I/O

## Forbidden imports

`lib.application.*`

## Files

| File | Purpose |
|------|---------|
| `host.py` | Host-plane operations |
| `container.py` | Container-plane operations |
| `mutex.py` | Mount / framework mutex |
| `lifecycle.py` | Plane lifecycle helpers |
| `platform_runner.py` | Platform process runner |
| `post_start.py` | Post-start hooks |
| `probe.py` | Health probes |
| `__init__.py` | `build_host_plane` / `build_container_plane` / `build_mutex` |
