"""Management plane adapters (Wave1.5)."""
from __future__ import annotations

from lib.adapters.plane.container import ContainerPlane
from lib.adapters.plane.host import HostPlane
from lib.adapters.plane.mutex import FileMountMutex
from lib.ports.plane import ContainerPlanePort, HostPlanePort, MountMutex


def build_host_plane(data_dir: str) -> HostPlanePort:
    return HostPlane(data_dir)


def build_container_plane(data_dir: str) -> ContainerPlanePort:
    return ContainerPlane(data_dir)


def build_mutex(frameworks: dict | None = None) -> MountMutex:
    return FileMountMutex(frameworks)


__all__ = [
    "ContainerPlane",
    "FileMountMutex",
    "HostPlane",
    "build_container_plane",
    "build_host_plane",
    "build_mutex",
]
