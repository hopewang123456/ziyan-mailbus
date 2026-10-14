"""容器内配置生成（Codex / OpenClaw）+ resolve_container。"""
from lib.adapters.container.resolver import (
    container_for_service,
    container_prefix,
    resolve_container,
)

__all__ = [
    "container_for_service",
    "container_prefix",
    "resolve_container",
]
