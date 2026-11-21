"""运行期配置。路径只在这里出现。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data"


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("MAILBUS_DATA_DIR") or _DEFAULT_DATA_DIR)
    )
    dispatch_interval_sec: float = 5.0
    dispatch_batch: int = 50
    dispatch_max_attempts: int = 3
    heartbeat_timeout_sec: float = 180.0
    heartbeat_sweep_interval_sec: float = 30.0
    sse_max_streams: int = 256
    public_screen_limit: int = 64
    max_body_bytes: int = 1_048_576
    retention_days: float = 7.0
    maintenance_interval_sec: float = 3600.0

    @property
    def db_path(self) -> Path:
        return self.data_dir / "mailbus.db"

    @property
    def file_bus_dir(self) -> Path:
        return self.data_dir / "file_bus"

    @property
    def mcp_dir(self) -> Path:
        return self.data_dir / "mcp"

    @property
    def layout_path(self) -> Path:
        """只读空间种子；路径只在本层出现。"""
        return Path(__file__).resolve().parents[3] / "config" / "office-layout.json"

    @property
    def settings_store_path(self) -> Path:
        """集成 env 与插件清单的可写配置。"""
        return self.data_dir / "settings.json"

    @property
    def metrics_manifest_path(self) -> Path:
        """指标口径 SoT；随仓库分发，只读。"""
        return (
            Path(__file__).resolve().parents[3]
            / "shared"
            / "config"
            / "mailbus"
            / "metrics-manifest.json"
        )

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = os.environ.get("MAILBUS_DATA_DIR")
        return cls(
            data_dir=Path(data_dir) if data_dir else _DEFAULT_DATA_DIR,
            dispatch_interval_sec=float(os.environ.get("MAILBUS_DISPATCH_INTERVAL_SEC", "5")),
            dispatch_batch=int(os.environ.get("MAILBUS_DISPATCH_BATCH", "50")),
            dispatch_max_attempts=int(os.environ.get("MAILBUS_DISPATCH_MAX_ATTEMPTS", "3")),
            heartbeat_timeout_sec=float(
                os.environ.get("MAILBUS_HEARTBEAT_TIMEOUT_SEC", "180")
            ),
            heartbeat_sweep_interval_sec=float(
                os.environ.get("MAILBUS_HEARTBEAT_SWEEP_SEC", "30")
            ),
            sse_max_streams=int(os.environ.get("MAILBUS_SSE_MAX_STREAMS", "256")),
            public_screen_limit=int(os.environ.get("MAILBUS_PUBLIC_SCREEN_LIMIT", "64")),
            max_body_bytes=int(
                os.environ.get("MAILBUS_MAX_BODY_BYTES", str(1_048_576))
            ),
            retention_days=float(os.environ.get("MAILBUS_RETENTION_DAYS", "7")),
            maintenance_interval_sec=float(
                os.environ.get("MAILBUS_MAINTENANCE_INTERVAL_SEC", "3600")
            ),
        )
