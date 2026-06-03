"""
ziyan-mailbus 全局常量与路径

所有硬编码路径统一收口到这里。
"""

import os
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ── 项目根目录 ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # mailbus/lib/ → mailbus/
PROJECT_ROOT_STR = str(PROJECT_ROOT)

# ── 数据目录 ─────────────────────────────────────────────────────────────
DEFAULT_DATA_DIR = os.path.join(PROJECT_ROOT_STR, "store")
DEFAULT_INBOX_BASE = f"{DEFAULT_DATA_DIR}/inbox"
DEFAULT_LOG_DIR = os.path.join(PROJECT_ROOT_STR, "logs")

# ── 默认配置 ─────────────────────────────────────────────────────────────
DEFAULT_ACK_TIMEOUT = 10
DEFAULT_MAX_RETRIES = 3
DEFAULT_ARCHIVE_DAYS = 7
DEFAULT_ARCHIVE_MAX_MESSAGES = 300
DEFAULT_POLL_INTERVAL = 15

# ── 版本号 ──────────────────────────────────────────────────────────────
# 当前 mailbus 代码版本。每次不兼容更新递增。
# 用于自动迁移旧配置到新版。
MAILBUS_VERSION = "2.1.0"
DEFAULT_HEARTBEAT_INTERVAL = 60

# ── 全局锁文件 ───────────────────────────────────────────────────────────
LOCK_FILE = "/tmp/ziyan-mailbus.lock"


# ── 工具函数 ──────────────────────────────────────────────────────────

TZ_CST = timezone(timedelta(hours=8))


def _now_iso() -> str:
    """返回当前时间的 ISO 格式字符串（本地时间 +08:00）"""
    return datetime.now(TZ_CST).strftime("%Y-%m-%dT%H:%M:%S%z")
