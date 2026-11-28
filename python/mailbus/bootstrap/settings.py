"""运行期配置。路径只在这里出现。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_DATA_DIR = _REPO_ROOT / "data"
# 约定：前端构建产物与后端同仓分发（web/dist，已 gitignore）
_DEFAULT_WEB_DIST = _REPO_ROOT / "web" / "dist"

_OFF_VALUES = {"", "0", "off", "none", "false"}


def _resolve_web_dist() -> Path | None:
    """前端静态目录：默认取 <仓库根>/web/dist，存在才托管。

    - MAILBUS_WEB_DIST 未设置：dist 存在则托管，否则不托管（纯 API 模式）
    - MAILBUS_WEB_DIST=off/none/0：强制关闭
    - 其他值：绝对路径或相对仓库根的路径
    """
    raw = os.environ.get("MAILBUS_WEB_DIST")
    if raw is not None:
        value = raw.strip()
        if value.lower() in _OFF_VALUES:
            return None
        path = Path(value)
        return path if path.is_absolute() else _REPO_ROOT / path
    return _DEFAULT_WEB_DIST if _DEFAULT_WEB_DIST.is_dir() else None


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("MAILBUS_DATA_DIR") or _DEFAULT_DATA_DIR)
    )
    dispatch_interval_sec: float = 5.0
    dispatch_batch: int = 50
    dispatch_max_attempts: int = 3
    heartbeat_timeout_sec: float = 90.0
    heartbeat_sweep_interval_sec: float = 30.0
    sse_max_streams: int = 256
    public_screen_limit: int = 64
    max_body_bytes: int = 1_048_576
    max_upload_bytes: int = 100 * 1024 * 1024
    retention_days: float = 7.0
    maintenance_interval_sec: float = 3600.0
    bootstrap_allow_remote: bool = False
    # 同源静态托管（web/dist）；默认随安装目录的相对路径，存在才托管
    web_dist: Path | None = field(default_factory=_resolve_web_dist)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "mailbus.db"

    @property
    def file_bus_dir(self) -> Path:
        return self.data_dir / "file_bus"

    @property
    def artifacts_dir(self) -> Path:
        path = self.data_dir / "artifacts"
        path.mkdir(parents=True, exist_ok=True)
        return path

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
                os.environ.get("MAILBUS_HEARTBEAT_TIMEOUT_SEC", "90")
            ),
            heartbeat_sweep_interval_sec=float(
                os.environ.get("MAILBUS_HEARTBEAT_SWEEP_SEC", "30")
            ),
            sse_max_streams=int(os.environ.get("MAILBUS_SSE_MAX_STREAMS", "256")),
            public_screen_limit=int(os.environ.get("MAILBUS_PUBLIC_SCREEN_LIMIT", "64")),
            max_body_bytes=int(
                os.environ.get("MAILBUS_MAX_BODY_BYTES", str(1_048_576))
            ),
            max_upload_bytes=int(
                os.environ.get("MAILBUS_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024))
            ),
            retention_days=float(os.environ.get("MAILBUS_RETENTION_DAYS", "7")),
            maintenance_interval_sec=float(
                os.environ.get("MAILBUS_MAINTENANCE_INTERVAL_SEC", "3600")
            ),
            bootstrap_allow_remote=os.environ.get(
                "MAILBUS_BOOTSTRAP_ALLOW_REMOTE", "0"
            )
            == "1",
        )
