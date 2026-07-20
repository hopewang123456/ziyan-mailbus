"""
ziyan-mailbus 全局常量与路径

所有硬编码路径统一收口到这里。

本地（本机开发）：
  mail/skills|rules|plans|docs 等应为 junction → Obsidian Vault（见 Agent/_architecture）。
  默认 MAILBUS_*_ROOT = 仓库内相对路径即可，经 junction 读到 Vault 真源。
  不要用 .env 把知识根指到 Vault（避免与 junction 双源）。

GitHub / CI：
  未设 env 时默认仓库内 demo 路径；需要时用 MAILBUS_*_ROOT / TEAM_PACK_*_ROOT 覆盖到仓库相对根。
"""

import os
from pathlib import Path
from datetime import datetime, timezone, timedelta


def _env_path(key: str, default: Path) -> Path:
    raw = (os.environ.get(key) or "").strip()
    return Path(raw) if raw else default


# ── 项目根目录 ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # mail/lib/ → mail/
PROJECT_ROOT_STR = str(PROJECT_ROOT)
MAILBUS_ROOT = _env_path("MAILBUS_ROOT", PROJECT_ROOT)
MAILBUS_ROOT_STR = str(MAILBUS_ROOT)

_REPO_PARENT = MAILBUS_ROOT.parent
TEAM_PACK_ROOT = _env_path("TEAM_PACK_ROOT", _REPO_PARENT / "team-pack")
TEAM_PACK_ROOT_STR = str(TEAM_PACK_ROOT)

# ── 知识库根目录（默认 = 仓库内路径；本地靠 junction 进 Vault）──────────
# CI/publish 才用 env 覆盖，例如：
#   MAILBUS_SKILLS_ROOT=./skills
MAILBUS_SKILLS_ROOT = _env_path("MAILBUS_SKILLS_ROOT", MAILBUS_ROOT / "skills")
MAILBUS_RULES_ROOT = _env_path("MAILBUS_RULES_ROOT", MAILBUS_ROOT / "rules")
MAILBUS_PLANS_ROOT = _env_path("MAILBUS_PLANS_ROOT", MAILBUS_ROOT / "plans")
MAILBUS_DOCS_ROOT = _env_path("MAILBUS_DOCS_ROOT", MAILBUS_ROOT / "docs")
MAILBUS_IDENTITIES_ROOT = _env_path("MAILBUS_IDENTITIES_ROOT", MAILBUS_ROOT / "identities")

TEAM_PACK_SKILLS_ROOT = _env_path("TEAM_PACK_SKILLS_ROOT", TEAM_PACK_ROOT / "skills")
TEAM_PACK_RULES_ROOT = _env_path("TEAM_PACK_RULES_ROOT", TEAM_PACK_ROOT / "rules")

# Agent Vault 根：compose 挂载 profiles 软链目标用（本地默认路径，非「用 env 指知识库」）
# Docker 内 Hermes profile skills 常 symlink 到此树，容器需同路径 bind-mount。
_default_vault = Path("E:/Obsidian/Vaults/Agent")
if not (os.environ.get("AGENT_VAULT_ROOT") or "").strip():
    # 若 MAILBUS_SKILLS_ROOT 已是 …/Agent/skills/mailbus（junction 解析后），可推断
    try:
        if MAILBUS_SKILLS_ROOT.name == "mailbus" and MAILBUS_SKILLS_ROOT.parent.name == "skills":
            _default_vault = MAILBUS_SKILLS_ROOT.parent.parent
    except Exception:
        pass
AGENT_VAULT_ROOT = _env_path("AGENT_VAULT_ROOT", _default_vault)

MAILBUS_SKILLS_ROOT_STR = str(MAILBUS_SKILLS_ROOT)
MAILBUS_RULES_ROOT_STR = str(MAILBUS_RULES_ROOT)
MAILBUS_PLANS_ROOT_STR = str(MAILBUS_PLANS_ROOT)
MAILBUS_DOCS_ROOT_STR = str(MAILBUS_DOCS_ROOT)
MAILBUS_IDENTITIES_ROOT_STR = str(MAILBUS_IDENTITIES_ROOT)
TEAM_PACK_SKILLS_ROOT_STR = str(TEAM_PACK_SKILLS_ROOT)
TEAM_PACK_RULES_ROOT_STR = str(TEAM_PACK_RULES_ROOT)

# ── 数据目录 ─────────────────────────────────────────────────────────────
DEFAULT_DATA_DIR = os.environ.get("MAILBUS_DATA") or os.path.join(MAILBUS_ROOT_STR, "store")
MAILBUS_DATA_STR = DEFAULT_DATA_DIR
DEFAULT_INBOX_BASE = f"{DEFAULT_DATA_DIR}/inbox"
DEFAULT_LOG_DIR = os.path.join(MAILBUS_ROOT_STR, "logs")

# ── 默认配置 ─────────────────────────────────────────────────────────────
DEFAULT_ACK_TIMEOUT = 10
DEFAULT_MAX_RETRIES = 3
DEFAULT_REMINDER_MINUTES = 30
DEFAULT_MAX_REMINDERS = 12
DEFAULT_PUSH_COOLDOWN_MINUTES = 10
DEFAULT_MAX_PUSHES_PER_MESSAGE = 5
DEFAULT_ARCHIVE_DAYS = 7
DEFAULT_ARCHIVE_MAX_MESSAGES = 300
DEFAULT_POLL_INTERVAL = 15
DEFAULT_CLI_MSG_MAX_CHARS = 600
DEFAULT_API_TOKEN_ENV = "MAILBUS_API_TOKEN"
DEFAULT_API_PORT = 9814
DEFAULT_API_HOST = "127.0.0.1"
DEFAULT_API_BASE = f"http://{DEFAULT_API_HOST}:{DEFAULT_API_PORT}"

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
