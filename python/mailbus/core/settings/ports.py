"""外部集成与运行配置的存储端口（由 adapters 实现）。"""

from __future__ import annotations

from typing import Protocol


class SettingsStorePort(Protocol):
    """键值型运行配置：env、插件清单等，统一落一个 JSON 文档。"""

    def read(self) -> dict:
        """读取完整配置；不存在时返回空文档。"""

    def write(self, data: dict) -> None:
        """原子覆盖写入。"""
